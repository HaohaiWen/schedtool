#!/usr/bin/env python3

import argparse, json, subprocess, sys, re, shutil
from multiprocessing import Pool


def parse_command_line():
    parser = argparse.ArgumentParser(
        description='llvm schedule model generator.')
    parser.add_argument('-o', default='-', help='output file')
    parser.add_argument('--xed', help='xed path')
    parser.add_argument('--jf',
                        default='-',
                        help='instruction sched info json file')
    return parser.parse_args()


ignore_opcode_list = {
    'MOV64ao32': 'MOV64rm',
    'MOV64o32a': 'MOV64mr',
}

invalid_opcode_list = ['INVLPGB32', 'LOCK_PREFIX']


def fix_asm(opcode, asm_string, modes):
    vex2_asm_string = f'{{VEX2}} {asm_string}'
    vex3_asm_string = f'{{VEX3}} {asm_string}'
    evex_asm_string = f'{{EVEX}} {asm_string}'
    cmd_template = ("echo -e '{assembly}'"
                    "| llvm-mc --debug-only=print-opcode -o /dev/null")

    parsed_opcodes, best_parsed_opcodes, best_asm = None, None, None
    for mode in modes + [None]:
        asms = [vex2_asm_string, evex_asm_string, asm_string, vex3_asm_string]
        for asm in asms:
            if mode is not None:
                asm = f'.code{mode}\n{asm}'
            cmd = cmd_template.format(assembly=asm)
            try:
                result = subprocess.run(cmd,
                                        shell=True,
                                        check=True,
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.DEVNULL)
                parsed_opcodes = result.stdout.decode('utf-8').split(',')
            except:
                continue
            else:
                if opcode in parsed_opcodes:
                    if len(parsed_opcodes) == 1:
                        return opcode, asm

                    if (best_parsed_opcodes is None
                            or len(parsed_opcodes) < len(best_parsed_opcodes)):
                        best_parsed_opcodes = parsed_opcodes
                        best_asm = asm
                elif ignore_opcode_list.get(opcode, None) in parsed_opcodes:
                    return opcode, asm

    if best_parsed_opcodes is not None:
        return opcode, best_asm
    else:
        print(f"{modes}{cmd}\n'{opcode}': '{parsed_opcodes}',",
              file=sys.stderr)
        return opcode, asm_string


def encode_asm(opcode, asm_string):
    result = None

    # Try to match not CodeGenOnly opcode.
    try:
        cmd = f"echo -e '{asm_string}' | llvm-mc --show-encoding"
        result = subprocess.run(cmd,
                                shell=True,
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
    # Try to match CodeGenOnly opcodes.
    except subprocess.CalledProcessError:
        cmd = f"echo -e '{asm_string}' |" \
               "llvm-mc --show-encoding -debug-only=print-opcode"
        result = subprocess.run(cmd,
                                shell=True,
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)

    output = result.stdout.decode('utf-8').split('\n')
    for line in output:
        line = line.strip()
        match = re.match('.*# encoding: \[(.*)\]', line)
        if match:
            encoding = match.group(1).split(',')
            break
    encoding_str = ''
    for byte in encoding:
        encoding_str += f'{int(byte, 16):02x}'
    return (opcode, encoding_str)


def get_xed_info(opcode, encoding, mode):
    xed = args.xed or 'xed'
    assert shutil.which(xed) is not None, f'{xed} not found'

    result = None
    for m in [mode, 64, 32, 16]:
        try:
            cmd = f'{xed} -{m} -v 4 -d "{encoding}"'
            result = subprocess.run(cmd,
                                    shell=True,
                                    check=False,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE)
            output = result.stdout.decode('utf-8')
            output = output.split('\n')
            operands_info = []
            line_no = 3
            while not output[line_no].startswith('EOSZ:'):
                opi, infos = output[line_no].split()
                assert int(opi) == len(operands_info)
                infos = infos.split('/')
                operands_info.append({
                    'Name': infos[0],
                    'XType': infos[-2].lower(),
                    'Width': int(infos[-1]),
                })
                line_no += 1

            eosz = int(re.match('EOSZ:\s*(.*)', output[line_no]).group(1))
            iclass = re.match('ICLASS:\s*(.*)', output[line_no + 2]).group(1)
            category = re.match('CATEGORY:\s*(.*)',
                                output[line_no + 3]).group(1)
            extension = re.match('EXTENSION:\s*(.*)',
                                 output[line_no + 4]).group(1)
            iform = re.match('IFORM:\s*(.*)', output[line_no + 5]).group(1)
            isa_set = re.match('ISA_SET:\s*(.*)', output[line_no + 6]).group(1)
            return (opcode, {
                'EOSZ': eosz,
                'IClass': iclass,
                'Category': category,
                'Extension': extension,
                'IForm': iform,
                'IsaSet': isa_set,
                'OpdsInfo': operands_info,
            })

        except:
            continue
    else:
        print(f'[{opcode}]error ', cmd, file=sys.stderr)
        return (opcode, None)


if __name__ == '__main__':
    args = parse_command_line()
    ostream = sys.stdout if args.o == '-' else open(args.o, 'w')
    istream = sys.stdin if args.jf == '-' else open(args.jf, 'r')
    instr_sched_info = json.load(istream)

    # Fix asm strings.
    task_args = []
    for opcode, info in instr_sched_info.items():
        asm_string = info.get('AsmString', None)
        if asm_string is not None and opcode not in invalid_opcode_list:
            task_args.append([opcode, asm_string, info['Modes']])
    with Pool() as pool:
        result = pool.starmap(fix_asm, task_args)
    for opcode, asm in result:
        instr_sched_info[opcode]['AsmString'] = asm

    # Encode assembly.
    task_args = []
    for opcode, info in instr_sched_info.items():
        asm_string = info.get('AsmString', None)
        if asm_string is not None and opcode not in invalid_opcode_list:
            task_args.append([opcode, asm_string])
    with Pool() as pool:
        result = pool.starmap(encode_asm, task_args)
    for opcode, encoding_str in result:
        instr_sched_info[opcode]['Encoding'] = encoding_str

    # Add xed info.
    task_args = []
    for opcode, info in instr_sched_info.items():
        encoding = info.get('Encoding', None)
        if encoding is not None:
            asm_string = info['AsmString']
            match = re.match(r'.*\.code(\d{2})', asm_string)
            mode = 32
            if match:
                mode = int(match.group(1))
            task_args.append((opcode, encoding, mode))
    with Pool() as pool:
        result = pool.starmap(get_xed_info, task_args)
    for opcode, xed_info in result:
        if xed_info:
            instr_sched_info[opcode]['XedInfo'] = xed_info

    json.dump(instr_sched_info, ostream, indent=2)
    istream.close()
    ostream.close()
