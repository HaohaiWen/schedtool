#!/usr/bin/env python3

import argparse, json, sys, os, re

# Add parent dir to path.
sys.path.append(f'{os.path.dirname(os.path.realpath(__file__))}/..')

from schedver.schedver import get_smv_instrs
from lib import target
from lib.llvm_instr import Port


def parse_command_line():
    parser = argparse.ArgumentParser(description='Add llvm-smv uops info.')
    parser.add_argument('-o', default='-', help='output file')
    parser.add_argument('--ref-cpu', required=True, help='reference cpu')
    parser.add_argument('--target-cpu', required=True, help='target cpu')
    parser.add_argument('--overwrite',
                        default=False,
                        action='store_true',
                        help='Overwrite info if it existed')
    parser.add_argument('--jf',
                        default='-',
                        help='instruction sched info json file')
    return parser.parse_args()


def map_resources(opcode, ref_resources, ref_cpu, target_cpu):
    target_resources = []
    if (isinstance(ref_cpu, target.SkylakeServer)
            and isinstance(target_cpu, target.SapphireRapids)):
        for res in ref_resources:
            if res == ref_cpu.load_ports:
                target_resources.append(target_cpu.load_ports)
            elif res == Port.gets((2, 3, 7)):
                target_resources.append(Port.gets((7, 8)))
            elif res == Port.gets((4, )):
                target_resources.append(Port.gets((4, 9)))
            elif (res == Port.gets((0, 1, 5, 6))
                  and re.match(r'^(ADD|SUB|XOR|AND|OR)\d', opcode)):
                target_resources.append(Port.gets((0, 1, 5, 6, 10)))
            target_resources.append(res)
        return tuple(target_resources)
    elif (isinstance(ref_cpu, target.IcelakeServer)
          and isinstance(target_cpu, target.SapphireRapids)):
        for res in ref_resources:
            if res == ref_cpu.load_ports:
                target_resources.append(target_cpu.load_ports)
            elif res == Port.gets((2, 3, 7)):  # STA from SKX
                target_resources.append(Port.gets((7, 8)))
            elif res == Port.gets((4, )):  # STD from SKX
                target_resources.append(Port.gets((4, 9)))
            elif (res == Port.gets((0, 1, 5, 6))
                  and re.match(r'^(ADD|SUB|XOR|AND|OR)\d', opcode)):
                target_resources.append(Port.gets((0, 1, 5, 6, 10)))
            target_resources.append(res)
        return tuple(target_resources)
    elif (isinstance(ref_cpu, target.Skylake)
          and isinstance(target_cpu, target.AlderlakeP)):
        for res in ref_resources:
            if res == ref_cpu.load_ports:
                target_resources.append(target_cpu.load_ports)
            elif res == Port.gets((2, 3, 7)):
                target_resources.append(Port.gets((7, 8)))
            elif res == Port.gets((4, )):
                target_resources.append(Port.gets((4, 9)))
            elif (res == Port.gets((0, 1, 5, 6))
                  and re.match(r'^(ADD|SUB|XOR|AND|OR)\d', opcode)):
                target_resources.append(Port.gets((0, 1, 5, 6, 10)))
            target_resources.append(res)
        return tuple(target_resources)
    else:
        raise NotImplementedError(
            f'Unknown resources map between '
            f'{ref_cpu.proc_name} and {target_cpu.proc_name}')


if __name__ == '__main__':
    args = parse_command_line()
    istream = sys.stdin if args.jf == '-' else open(args.jf, 'r')
    ostream = sys.stdout if args.o == '-' else open(args.o, 'w')

    ref_cpu = target.get_target(args.ref_cpu)
    target_cpu = target.get_target(args.target_cpu)
    instr_sched_info = json.load(istream)
    for smv_instr in get_smv_instrs(ref_cpu):
        # FIXME: we assume each uop only consume 1 cycle.
        ports = []
        opcode = smv_instr.opcode
        for resources, cycles in zip(
                map_resources(opcode, smv_instr.resources, ref_cpu,
                              target_cpu), smv_instr.resource_cycles):
            ports.append([cycles, [int(str(p)) for p in resources]])
        sig_name = f'smv.{ref_cpu.proc_name}'
        uops = smv_instr.num_uops
        tp = smv_instr.throughput
        latency = smv_instr.latency
        uops_info = {'Port': ports, 'Uops': uops, 'Tp': tp, 'Latency': latency}
        info = instr_sched_info[smv_instr.opcode]
        if 'XedInfo' not in info:
            continue
        for key, value in uops_info.items():
            # Only add smv uops info to instruction with iform.
            if args.overwrite or key not in info:
                info[key] = value
                assert info.get(f'{key}Sig', None) != sig_name
                info[f'{key}Sig'] = sig_name
        # if port is updated then uops must be consistent with port.
        if info['PortSig'] == sig_name:
            info['Uops'] = uops_info['Uops']
            info['UopsSig'] = sig_name

    json.dump(instr_sched_info, ostream, indent=2)
    istream.close()
    ostream.close()
