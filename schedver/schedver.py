import sys, os, json, subprocess
from lib import target
from lib.info_parser import parse_smv_instr_info, parse_llvm_instr_info
from lib.llvm_instr import *


def get_smv_instrs(target_cpu):
    smv_instrs_json = subprocess.run(
        f'llvm-smv -mcpu={target_cpu.proc_name}',
        shell=True,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL).stdout.decode('utf-8')
    return parse_smv_instr_info(json.loads(smv_instrs_json), target_cpu)


class LLVMSchedVerifier:
    def __init__(self, llvm_instrs, target_cpu):
        self.target_cpu = target_cpu
        self.llvm_instrs = llvm_instrs
        self.smv_instrs = get_smv_instrs(target_cpu)

    def run(self):
        opc2smv_instrs = {
            smv_instr.opcode: smv_instr
            for smv_instr in self.smv_instrs
        }

        for llvm_instr in self.llvm_instrs:
            if (not llvm_instr.has_uops_info()
                    or llvm_instr.is_invalid(self.target_cpu)):
                continue

            uops_info = llvm_instr.uops_info
            smv_instr = opc2smv_instrs[llvm_instr.opcode]
            assert uops_info.latency == smv_instr.latency
            assert uops_info.num_uops == smv_instr.num_uops

            # FIXME: We assume each uops consumes only 1 cycles.
            res_cycles = {
                ports: cycles
                for ports, cycles in zip(smv_instr.resources,
                                         smv_instr.resource_cycles)
            }
            assert set(smv_instr.resources) == set(uops_info.ports)
            for ports in uops_info.ports:
                res_cycles[ports] -= 1
            assert all(cycs == 0 for cycs in res_cycles.values())
        print('Pass')


def main(args):
    target_cpu = target.get_target(args.target_cpu)
    with open(args.jf) as jf:
        llvm_instrs = parse_llvm_instr_info(json.load(jf), target_cpu)
    LLVMSchedVerifier(llvm_instrs, target_cpu).run()
