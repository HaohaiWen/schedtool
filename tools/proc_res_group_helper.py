#!/usr/bin/env python3

import argparse, json, sys, os, math

# Add parent dir to path.
sys.path.append(f'{os.path.dirname(os.path.realpath(__file__))}/..')

from lib import target, llvm_instr, info_parser


def parse_command_line():
    parser = argparse.ArgumentParser(
        description='Helper to define ProcResGroup.')
    parser.add_argument('--target-cpu', required=True, help='target cpu')
    parser.add_argument('--jf',
                        default='-',
                        help='instruction sched info json file')
    return parser.parse_args()


if __name__ == '__main__':
    args = parse_command_line()
    istream = sys.stdin if args.jf == '-' else open(args.jf, 'r')
    target_cpu = target.get_target(args.target_cpu)
    llvm_instrs = info_parser.parse_llvm_instr_info(json.load(istream),
                                                    target_cpu)
    ports_set = set()
    for llvm_instr in llvm_instrs:
        if (llvm_instr.has_uops_info()
                and not llvm_instr.is_invalid(target_cpu)):
            for uop in llvm_instr.uops_info.uops:
                ports_set.add(uop.ports)
    ports_groups = sorted(p for p in ports_set if len(p) > 1)
    aligned_width = math.ceil(
        (max(len(target_cpu.get_ports_name(p))
             for p in ports_groups) + 1) / 2) * 2
    for pg in ports_groups:
        pg_name = target_cpu.get_ports_name(pg)
        res = f'def {pg_name}' + ' ' * (aligned_width - len(pg_name))
        p_names = [target_cpu.get_ports_name((p, )) for p in pg]
        print(res + ': ProcResGroup<[' + ', '.join(p_names) + ']>;')

    istream.close()
