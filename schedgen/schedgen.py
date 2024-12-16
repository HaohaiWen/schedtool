import json, collections, sys

import lib.target as target
import lib.utils as utils
from lib.info_parser import parse_llvm_instr_info
from lib.llvm_instr import *


class LLVMSchedGen:
    def __init__(self, llvm_instrs, target_cpu):
        self.target_cpu = target_cpu
        self.llvm_instrs = llvm_instrs
        self.clean_wrong_schedwrite()
        self.infer_schedwrite_resources()
        self.infer_schedwriteres()
        self.validate_infered_resource()
        self.tag_unsupported_schedwrite()

    def gen_scheduler(self, ostream):
        self.emit_scheduler(ostream)

    def clean_wrong_schedwrite(self):
        ''' Some schedwrites of instr are wrong which must be removed. '''
        for llvm_instr in self.llvm_instrs:
            if not llvm_instr.has_uops_info():
                continue
            instr_latency = llvm_instr.uops_info.latency
            instr_ports = llvm_instr.uops_info.ports
            instr_num_uops = llvm_instr.uops_info.num_uops
            wrong_aux_schedwrites, wrong_writesequences = [], []
            for schedwrite in llvm_instr.schedwrites:
                if schedwrite.is_aux():
                    assert schedwrite.is_complete()
                    if (schedwrite.latency > instr_latency
                            or schedwrite.num_uops > instr_num_uops
                            or not utils.listcontain(instr_ports,
                                                     schedwrite.resources)):
                        wrong_aux_schedwrites.append(schedwrite)
                elif type(schedwrite) is WriteSequence:
                    ext_latency, ext_num_uops, ext_ports = 0, 0, []
                    for leaf_write in schedwrite.expand():
                        if not leaf_write.is_complete():
                            continue
                        ext_latency += leaf_write.latency
                        ext_num_uops += leaf_write.num_uops
                        ext_ports.extend(leaf_write.resources)
                    if (ext_latency > instr_latency
                            or ext_num_uops > instr_num_uops
                            or not utils.listcontain(instr_ports, ext_ports)):
                        wrong_writesequences.append(schedwrite)

            # Wrong aux schedwrite must be removed.
            if len(wrong_aux_schedwrites):
                llvm_instr.set_use_instrw(True)
                for wrong_sw in wrong_aux_schedwrites:
                    llvm_instr.schedwrites.remove(wrong_sw)

            # Wrong writesequence is replaced to WriteZero. infer_schedwriteres
            # will replace WriteZero to SchedWriteRes.
            if len(wrong_writesequences):
                llvm_instr.set_use_instrw(True)
                for wrong_ws in wrong_writesequences:
                    llvm_instr.replace_or_add_schedrw(wrong_ws,
                                                      SchedWrite('WriteZero'),
                                                      not_null=True)

    def infer_schedwrite_resources(self):
        ''' Infer resources, latency def for schedwrite. '''
        # Map from schedwrite to associated llvm_instrs.
        sw2instrs = {}
        for llvm_instr in self.llvm_instrs:
            for schedwrite in llvm_instr.schedwrites:
                sw2instrs.setdefault(schedwrite, []).append(llvm_instr)

        # TODO: resource_cycles is not derived.
        for schedwrite, llvm_instrs in sw2instrs.items():
            if schedwrite.is_complete():
                continue
            candidates = []
            for llvm_instr in llvm_instrs:
                if not llvm_instr.has_uops_info():
                    continue
                dr_latency = llvm_instr.uops_info.latency
                dr_num_uops = llvm_instr.uops_info.num_uops
                dr_ports = llvm_instr.uops_info.ports
                for instr_sw in llvm_instr.schedwrites:
                    if instr_sw == schedwrite:
                        continue
                    assert instr_sw.is_complete() and instr_sw.is_aux(), \
                        f'[{schedwrite}, {instr_sw}] only 1 incompleted ' \
                        f'schedwrite is allowed.'
                    dr_num_uops -= instr_sw.num_uops
                    dr_ports = utils.listremove(dr_ports, instr_sw.resources)
                dr_ports = tuple(sorted(dr_ports))
                candidates.append((dr_latency, dr_num_uops, dr_ports))

            # Pick up a choice for schedwrite.
            choices = collections.Counter(candidates).most_common()
            if len(choices):
                for choice, cnt in choices:
                    # If latency, num_uops >= 0.
                    if choice[0] >= 0 and choice[1] >= 0:
                        best_choice = choice
                        break
                else:
                    raise ValueError('Not find best choice.')

                dr_latency = best_choice[0]
                dr_num_uops = best_choice[1]
                dr_ports = best_choice[2]

                write = schedwrite
                if type(schedwrite) is WriteSequence:
                    write = None
                    leaf_writes = schedwrite.expand()
                    for leaf_write in leaf_writes:
                        if leaf_write.is_complete():
                            dr_latency -= leaf_write.latency
                            dr_num_uops -= leaf_write.num_uops
                            dr_ports = utils.listremove(
                                dr_ports, leaf_write.resources)
                            continue
                        assert write is None, (f'multi leaf schedwrite'
                                               f'incompleted: {leaf_writes}')
                        write = leaf_write
                    dr_ports = tuple(sorted(dr_ports))

                # Set all resource_cycles to 1 cycle for convenience.
                write.set_resources(resources=dr_ports,
                                    resource_cycles=(1, ) * len(dr_ports),
                                    num_uops=dr_num_uops,
                                    latency=dr_latency)

    def infer_schedwriteres(self):
        for llvm_instr in self.llvm_instrs:
            if not llvm_instr.has_uops_info():
                continue
            dr_latency = llvm_instr.uops_info.latency
            dr_num_uops = llvm_instr.uops_info.num_uops
            dr_ports = llvm_instr.uops_info.ports

            old_schedwrite = None
            for schedwrite in llvm_instr.schedwrites:
                if schedwrite.is_aux():
                    assert dr_latency >= schedwrite.latency
                    dr_num_uops -= schedwrite.num_uops
                    dr_ports = utils.listremove(dr_ports, schedwrite.resources)
                else:
                    assert old_schedwrite is None
                    old_schedwrite = schedwrite

            if (old_schedwrite and old_schedwrite.latency == dr_latency
                    and old_schedwrite.num_uops == dr_num_uops
                    and utils.cmplist(old_schedwrite.resources, dr_ports)):
                continue

            assert dr_num_uops >= 0
            dr_ports = tuple(sorted(dr_ports))
            schedwriteres = SchedWriteRes(resources=dr_ports,
                                          resource_cycles=(1, ) *
                                          len(dr_ports),
                                          latency=dr_latency,
                                          num_uops=dr_num_uops,
                                          prefix=self.target_cpu.short_name)
            llvm_instr.replace_or_add_schedrw(old_schedwrite, schedwriteres)
            llvm_instr.set_use_instrw(True)

    def validate_infered_resource(self):
        for llvm_instr in self.llvm_instrs:
            if not llvm_instr.has_uops_info():
                continue
            assert (
                llvm_instr.uops_info.latency == llvm_instr.compute_latency())
            assert (
                llvm_instr.uops_info.num_uops == llvm_instr.compute_num_uops())
            assert utils.cmplist(llvm_instr.uops_info.ports,
                                 llvm_instr.compute_resources())

    def tag_unsupported_schedwrite(self):
        sw2instrs = {}
        for llvm_instr in self.llvm_instrs:
            for schedwrite in llvm_instr.schedwrites:
                if type(schedwrite) is WriteSequence:
                    for leaf_write in schedwrite.expand():
                        sw2instrs.setdefault(leaf_write, []).append(llvm_instr)
                else:
                    sw2instrs.setdefault(schedwrite, []).append(llvm_instr)

        for schedwrite, llvm_instrs in sw2instrs.items():
            is_spt = len(llvm_instrs) == 0
            is_spt = is_spt or all(llvm_instr.isa_set is None
                                   for llvm_instr in llvm_instrs)
            is_spt = is_spt or not all(llvm_instr.isa_set is None or
                                       llvm_instr.is_invalid(self.target_cpu)
                                       for llvm_instr in llvm_instrs)
            schedwrite.set_supported(is_spt)

    def emit_scheduler(self, ostream):
        with open(self.target_cpu.template_td) as td:
            ostream.write(td.read())
        ostream.write(f'\n//==={"-"*70}===//\n')
        ostream.write('// The following definitons are infered by smg.\n')
        ostream.write(f'//==={"-"*70}===//\n\n')
        ostream.write('// Infered SchedWrite definition.\n')

        # Populate schedwrite and emit them.
        lived_schedwrites = set()
        for llvm_instr in self.llvm_instrs:
            for instr_sw in llvm_instr.schedwrites:
                if type(instr_sw) is WriteSequence:
                    for leaf_write in instr_sw.expand():
                        assert type(leaf_write) is SchedWrite
                        lived_schedwrites.add(leaf_write)
                elif type(instr_sw) is SchedWrite:
                    lived_schedwrites.add(instr_sw)
        dead_schedwrites = tuple(
            sorted(set(SchedWrite.get_all()) - lived_schedwrites))
        lived_schedwrites = collections.deque(sorted(lived_schedwrites))

        while len(lived_schedwrites):
            write = lived_schedwrites.popleft()
            write_mem = SchedWrite.get(write.name + 'Ld')
            writes = (write, )

            if write_mem:
                lived_schedwrites.remove(write_mem)
                writes = (write, write_mem)
                if all(not x.is_supported() for x in (write, write_mem)):
                    self.emit_write_res_pair_unsupported(ostream, write)
                    continue

                if all(x.is_complete() for x in (write, write_mem)):
                    if self.try_emit_write_res_pair(ostream, write, write_mem):
                        continue

            for schedwrite in writes:
                if not schedwrite.is_supported():
                    self.emit_write_res_unsupported(ostream, schedwrite)
                elif not schedwrite.is_complete():
                    ostream.write('// FIXME: Incompleted schedwrite.\n')
                    self.emit_write_res_unsupported(ostream, schedwrite)
                else:
                    self.emit_write_res(ostream, schedwrite)

        if len(dead_schedwrites):
            ostream.write('\n// Dead schedwrites that nobody uses.\n')
        for dead_write in dead_schedwrites:
            self.emit_write_res_unsupported(ostream, dead_write)

        # Group instrs which used InstRW based on schedrws.
        schedrws2instrs = {}
        for llvm_instr in self.llvm_instrs:
            if not llvm_instr.use_instrw():
                continue

            # SchedWriteRes comes first, then SchedWrite, SchedRead.
            schedrws = tuple(
                sorted(llvm_instr.schedreads + llvm_instr.schedwrites,
                       key=lambda x:
                       (type(x) is SchedRead, type(x) is SchedWrite, type(x) is
                        SchedWriteRes, x.name)))
            schedrws2instrs.setdefault(schedrws, []).append(llvm_instr)

        schedrws2instrs = dict(
            sorted(schedrws2instrs.items(), key=lambda x:
                   (x[0][0], len(x[0]))))

        # Emit SchedWriteRes and InstRW.
        ostream.write('\n// Infered SchedWriteRes and InstRW definition.\n')
        emitted = set()
        for schedrws, llvm_instrs in schedrws2instrs.items():
            for schedrw in schedrws:
                if type(schedrw) is SchedWriteRes and schedrw not in emitted:
                    emitted.add(schedrw)
                    ostream.write('\n')
                    self.emit_schedwriteres(ostream, schedrw)
            self.emit_instrw(ostream, schedrws, llvm_instrs)

        # Emit tailer bracket
        ostream.write('\n}\n')

    def emit_write_res_pair_unsupported(self, ostream, schedwrite):
        ostream.write(
            f'defm : X86WriteResPairUnsupported<{schedwrite.name}>;\n')

    def emit_write_res_unsupported(self, ostream, schedwrite):
        ostream.write(f'defm : X86WriteResUnsupported<{schedwrite.name}>;\n')

    def try_emit_write_res_pair(self, ostream, write_reg, write_mem):
        ports_diff = utils.listdiff(write_reg.resources, write_mem.resources)
        # Return false if ports_diff is empty or all diffs aren't load ports.
        if len(ports_diff) == 0 or any(port != self.target_cpu.load_ports
                                       for port in ports_diff):
            return False

        num_loads = len(ports_diff)
        if write_mem.num_uops - write_reg.num_uops != num_loads:
            return False

        short_name = self.target_cpu.short_name

        res_defs = collections.Counter(write_reg.resources).items()
        exe_ports = '[' + ', '.join(
            self.target_cpu.get_ports_name(res[0]) for res in res_defs) + ']'
        latstr = self.target_cpu.lat2str(write_reg.latency)

        load_lat = write_mem.latency - write_reg.latency
        if load_lat < 0:
            ostream.write('// Warning: negtive load latency.\n')

        ostream.write(f'defm : {short_name}WriteResPair<{write_reg.name}, '
                      f'{exe_ports}, {latstr}')
        tailer = '>;\n'
        must_present = False
        if num_loads != 1:
            tailer = f', {num_loads}' + tailer
            must_present = True
        if must_present or load_lat != self.target_cpu.load_latency:
            tailer = f', {load_lat}' + tailer
            must_present = True
        if must_present or write_reg.num_uops != 1:
            tailer = f', {write_reg.num_uops}' + tailer
            must_present = True
        if must_present or write_reg.resource_cycles != [1]:
            resource_cycles = '[' + ', '.join(str(res[1])
                                              for res in res_defs) + ']'
            tailer = f', {resource_cycles}' + tailer
        ostream.write(tailer)
        return True

    def emit_write_res(self, ostream, schedwrite):
        num_uops = schedwrite.num_uops
        res_defs = collections.Counter(schedwrite.resources).items()
        exe_ports = '[' + ', '.join(
            self.target_cpu.get_ports_name(res[0]) for res in res_defs) + ']'
        resource_cycles = tuple(res[1] for res in res_defs)
        latstr = self.target_cpu.lat2str(schedwrite.latency)

        if num_uops != 1:
            ostream.write(
                f'defm : X86WriteRes<{schedwrite.name}, {exe_ports}, '
                f'{latstr}, {list(resource_cycles)}, {num_uops}>;\n')
        else:
            ostream.write(f'def : WriteRes<{schedwrite.name}, {exe_ports}>')
            tailer = ''
            if resource_cycles != (1, ) * len(resource_cycles):
                tailer += f'  let ResourceCycles = {list(resource_cycles)};\n'
            if schedwrite.latency != 1:
                tailer += f'  let Latency = {latstr};\n'
            if tailer:
                tailer = ' {\n' + tailer + '}\n'
            else:
                tailer = ';\n'
            ostream.write(tailer)

    def emit_schedwriteres(self, ostream, schedwriteres):
        res_defs = collections.Counter(schedwriteres.resources).items()
        exe_ports = '[' + ', '.join(
            self.target_cpu.get_ports_name(res[0]) for res in res_defs) + ']'
        resource_cycles = tuple(res[1] for res in res_defs)
        latstr = self.target_cpu.lat2str(schedwriteres.latency)

        ostream.write(f'def {schedwriteres.name} : SchedWriteRes<{exe_ports}>')
        tailer = ''
        if resource_cycles != (1, ) * len(resource_cycles):
            tailer += f'  let ResourceCycles = {list(resource_cycles)};\n'
        if schedwriteres.latency != 1:
            tailer += f'  let Latency = {latstr};\n'
        if schedwriteres.num_uops != 1:
            tailer += f'  let NumMicroOps = {schedwriteres.num_uops};\n'
        if tailer:
            tailer = ' {\n' + tailer + '}\n'
        else:
            tailer = ';\n'
        ostream.write(tailer)

    def emit_instrw(self, ostream, schedrws, llvm_instrs):
        instrs_regexes, instrs_opcode = [], []

        for expr in utils.RegexReducer(4).reduce(
            [x.opcode for x in llvm_instrs]):
            if any(char in expr for char in ('(', ')', '|', '?', '*')):
                instrs_regexes.append(expr)
            else:
                instrs_opcode.append(expr)

        # Emit instregex.
        if instrs_regexes:
            header = 'def : InstRW<[' + ', '.join([x.name for x in schedrws
                                                   ]) + '], (instregex '
            ostream.write(header)
            indent = False
            for instrs_regex in instrs_regexes:
                if indent:
                    ostream.write(',\n' + ' ' * len(header))
                else:
                    indent = True
                ostream.write(f'"^{instrs_regex}$"')
            ostream.write(')>;\n')

        # Emit instrs.
        if instrs_opcode:
            header = 'def : InstRW<[' + ', '.join([x.name for x in schedrws
                                                   ]) + '], (instrs '
            ostream.write(header)
            indent = False
            for opcode in instrs_opcode:
                if indent:
                    ostream.write(',\n' + ' ' * len(header))
                else:
                    indent = True
                ostream.write(f'{opcode}')
            ostream.write(')>;\n')


def main(args):
    target_cpu = target.get_target(args.target_cpu)
    with open(args.jf) as jf:
        llvm_instrs = parse_llvm_instr_info(json.load(jf), target_cpu)

    ostream = sys.stdout if args.o == '-' else open(args.o, 'w')
    LLVMSchedGen(llvm_instrs, target_cpu).gen_scheduler(ostream)
    ostream.close()
