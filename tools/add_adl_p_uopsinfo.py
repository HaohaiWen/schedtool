#!/usr/bin/env python3

import argparse, json, sys, subprocess, math
from collections import Counter
from multiprocessing import Pool


def parse_command_line():
    parser = argparse.ArgumentParser(
        description='Add alderlake-p/sapphirerapids uops info from intel doc.')
    parser.add_argument('-o', default='-', help='output file')
    parser.add_argument('--overwrite',
                        default=False,
                        action='store_true',
                        help='Overwrite info if it existed')
    parser.add_argument('--jf',
                        default='-',
                        help='instruction sched info json file')
    parser.add_argument('--adl-p-json',
                        '--spr-json',
                        required=True,
                        help='alderlake-p/sapphirerapids tpt lat json file')
    return parser.parse_args()


def duops2ports(duops):
    uops_info = []
    for ports_desc, num_uops in Counter(item['ports']
                                        for item in duops).items():
        if ports_desc != '':
            ports = [int(i, 16) for i in ports_desc]
            uops_info.append([num_uops, ports])
    return uops_info


def disassemble(encode):
    blocks = []
    for i in range(math.ceil(len(encode) / 2)):
        blocks.append(f'0x{encode[2*i:2*i+2]}')
    formatted_encode = ','.join(blocks)
    triples = ('x86_64', 'i386', 'i686-linux-gnu-code16')
    for triple in triples:
        cmd = (f"echo -e '{formatted_encode}' | llvm-mc --disassemble "
               f"--triple={triple} --debug-only=print-opcode -o /dev/null")
        result = subprocess.run(cmd,
                                shell=True,
                                check=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.DEVNULL)
        parsed_opcode = result.stdout.decode('utf-8')
        if parsed_opcode != '':
            return encode, parsed_opcode
    return encode, None


if __name__ == '__main__':
    args = parse_command_line()
    ostream = sys.stdout if args.o == '-' else open(args.o, 'w')
    istream = sys.stdin if args.jf == '-' else open(args.jf, 'r')

    encode2uopsinfo = {}
    with open(args.adl_p_json) as adl_p_json:
        for info in json.load(adl_p_json):
            encode = info['uniq_key']
            assert encode not in encode2uopsinfo
            if (len(info.get('duops', [])) == 0
                    or all(item['ports'] == '' for item in info['duops'])):
                continue

            ports = duops2ports(info['duops'])
            est_uops = sum(item[0] for item in ports)
            uops = int(info.get('uops_number', est_uops))
            if uops < est_uops:
                print(f"{uniq_key} :",
                      f'uops derived from ports ({est_uops}) > '
                      f'uops listed ({uops}), use derived one',
                      file=sys.stderr)
                uops = est_uops
            tp = float(info['throughput']) if 'throughput' in info else None
            latency = (int(float(info['latency']))
                       if 'latency' in info else None)
            entry = {}
            for name, value in zip(('Port', 'Uops', 'Tp', 'Latency'),
                                   (ports, uops, tp, latency)):
                if value is not None:
                    entry[name] = value
            encode2uopsinfo[encode] = entry

    with Pool() as pool:
        result = pool.map(disassemble, encode2uopsinfo.keys())

    sig_name = 'hw-adl'
    instr_sched_info = json.load(istream)
    for encode, parsed_opcode in result:
        if parsed_opcode is None:
            continue
        sched_info = instr_sched_info[parsed_opcode]
        if 'XedInfo' not in sched_info:
            continue
        uops_info = encode2uopsinfo[encode]
        for key, value in uops_info.items():
            if args.overwrite or key not in sched_info:
                sched_info[key] = value
                assert sched_info.get(f'{key}Sig', None) != sig_name
                sched_info[f'{key}Sig'] = 'hw-adl'
        # if port is updated then uops must be consistent with port.
        if sched_info['PortSig'] == sig_name:
            sched_info['Uops'] = uops_info['Uops']
            sched_info['UopsSig'] = sig_name

    json.dump(instr_sched_info, ostream, indent=2)
    istream.close()
    ostream.close()
