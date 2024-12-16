from lib.llvm_instr import *
from lib import utils


def parse_llvm_instr_info(instr_info, target_cpu):
    def scan_schedwrite(write_desc):
        write_type = write_desc['Type']
        if write_type == 'SchedWrite' or write_type == 'X86FoldableSchedWrite':
            return SchedWrite(write_desc['Name'])
        elif write_type == 'WriteSequence':
            name = write_desc['Name']
            writes = [
                scan_schedwrite(next_desc)
                for next_desc in write_desc['Writes']
            ]
            repeat = write_desc['Repeat']
            return WriteSequence(name, writes, repeat)
        else:
            raise TypeError(f'Unknown schedwrite type: {write_type}')

    llvm_instrs = []
    for opcode, desc in instr_info.items():
        schedreads, schedwrites = [], []
        for read_desc in desc['SchedReads']:
            assert read_desc['Type'] == 'SchedRead', 'Unknown schedread type'
            schedreads.append(SchedRead(read_desc['Name']))
        for write_desc in desc['SchedWrites']:
            schedwrites.append(scan_schedwrite(write_desc))
        isa_set = desc['XedInfo']['IsaSet'] if 'XedInfo' in desc else None
        llvm_instr = LLVMInstr(opcode, schedreads, schedwrites, isa_set)
        if 'Port' in desc and not llvm_instr.is_invalid(target_cpu):
            uops = []
            latency = desc.get('Latency', target_cpu.max_latency)
            throughput = desc.get('Tp', None)
            for item in desc['Port']:
                uop = Uop(ports=[Port(pn) for pn in item[1]])
                assert all(Port(pn) is Port.INVALID_PORT or
                           Port(pn) in target_cpu.all_ports for pn in item[1]),\
                       f'Found invalid port in {item[1]}'
                uops.extend([uop] * item[0])
            num_uops = desc.get('Uops', len(uops))
            llvm_instr.set_uops_info(
                UopsInfo(latency, throughput, uops, num_uops))
        llvm_instrs.append(llvm_instr)
    return llvm_instrs


def infer_res(resources, resource_cycles):
    class Node:
        def __init__(self, res, cycs):
            self.res = res
            self.cycs = cycs
            self.next = []

    nodes = [
        Node(res, cycles) for res, cycles in zip(resources, resource_cycles)
    ]
    for node in nodes:
        for other in nodes:
            if other != node and utils.listcontain(other.res, node.res):
                node.next.append(other)
    nodes.sort(key=lambda x: len(x.next), reverse=True)
    for node in nodes:
        if node.cycs > 0:
            for next_node in node.next:
                assert next_node.cycs > 0
                next_node.cycs -= node.cycs

    leaf_res, leaf_res_cycs = [], []
    for node in nodes:
        if node.cycs > 0:
            leaf_res.append(node.res)
            leaf_res_cycs.append(node.cycs)
    return leaf_res, leaf_res_cycs


def parse_smv_instr_info(instr_info, target_cpu):
    smv_instrs = []
    for opcode, desc in instr_info.items():
        resources, resource_cycles = [], []
        for ports_name, cycles in desc['WriteRes'].items():
            resources.append(target_cpu.parse_ports_name(ports_name))
            resource_cycles.append(cycles)
        resources, resource_cycles = infer_res(resources, resource_cycles)
        smv_instrs.append(
            SMVInstr(opcode, int(desc['Latency']), int(desc['NumUops']),
                     float(desc['RThroughput']), resources, resource_cycles))
    return smv_instrs
