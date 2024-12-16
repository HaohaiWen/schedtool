#!/bin/python3

import argparse, json, sys, re
import xml.etree.ElementTree as ET


def parse_command_line():
    parser = argparse.ArgumentParser(
        description='llvm schedule model generator.')
    parser.add_argument('-o', default='-', help='output file')
    parser.add_argument('--jf',
                        default='-',
                        help='instruction sched info json file')
    parser.add_argument('--arch-name', required=True, help='architecture name')
    parser.add_argument('--overwrite',
                        default=False,
                        action='store_true',
                        help='Overwrite info if it existed')
    parser.add_argument('--inst-xml',
                        required=True,
                        help='uops.info instructions.xml file')
    parser.add_argument('--debug',
                        default=False,
                        action='store_true',
                        help='Print debug info')
    return parser.parse_args()


print('Warning: port 10 and port 11 are reversed on uops.info.',
      "Let's swap them.",
      file=sys.stderr)


# TODO: Update this method if uops.info changes ports representation.
def format_ports(ports_str):
    uops_info = []
    for uops_desc in ports_str.split('+'):
        num_uops, ports_desc = uops_desc.split('*')
        num_uops = int(num_uops)
        assert ports_desc[0] == 'p'
        ports = [int(i, 16) for i in ports_desc[1:]]

        # FIXME: Remove this code once uops.info reverse pA and pB.
        for i in range(len(ports)):
            if ports[i] == 10:
                ports[i] = 11
            elif ports[i] == 11:
                ports[i] = 10

        uops_info.append([num_uops, ports])
    return uops_info


class XmlInstrInfo:
    def __init__(self, attrib):
        self.attrib = attrib
        self.xml_operands_info = []
        self.xml_uops_info = None


if __name__ == '__main__':
    args = parse_command_line()
    ostream = sys.stdout if args.o == '-' else open(args.o, 'w')
    istream = sys.stdin if args.jf == '-' else open(args.jf, 'r')

    iform2xml_instr_infos = {}
    root = ET.parse(args.inst_xml).getroot()
    for extension in root:
        for instruction in extension:
            iform = instruction.attrib['iform']
            iclass = instruction.attrib['iclass']
            extension = instruction.attrib['extension']
            xml_instr_info = XmlInstrInfo(instruction.attrib)
            iform2xml_instr_infos.setdefault(iform, []).append(xml_instr_info)
            for instr_info in instruction:
                if instr_info.tag == 'operand':
                    xml_instr_info.xml_operands_info.append(instr_info.attrib)
                    continue

                if (instr_info.tag != 'architecture'
                        or instr_info.attrib['name'] != args.arch_name):
                    continue

                for perf_info in instr_info:
                    if perf_info.tag != 'measurement':
                        continue

                    uops = int(perf_info.attrib['uops'])
                    if uops > 1000000:
                        print(f'Skip invalid info :{perf_info.attrib}',
                              file=sys.stderr)
                        continue

                    ports = perf_info.attrib.get('ports', None)
                    if ports is not None:
                        ports = format_ports(ports)
                        est_uops = sum(item[0] for item in ports)
                        if uops < est_uops:
                            print(f"{instruction.attrib['string']} :",
                                  f'uops derived from ports ({est_uops}) > '
                                  f'uops measured ({uops}), use derived one',
                                  file=sys.stderr)
                            uops = est_uops
                    if uops == 0:
                        assert not ports
                        ports = []

                    tp = min(float(perf_info.attrib['TP_unrolled']),
                             float(perf_info.attrib['TP_loop']))
                    latency = -1
                    for child in perf_info:
                        for key, val in child.attrib.items():
                            if not re.match(r'^cycles((_)|(\w+))*$', key):
                                continue
                            latency = max(latency, int(val))
                    if latency == -1:
                        latency = None

                    entry = {}
                    for name, value in zip(('Port', 'Uops', 'Tp', 'Latency'),
                                           (ports, uops, tp, latency)):
                        if value is not None:
                            entry[name] = value
                    assert xml_instr_info.xml_uops_info is None
                    xml_instr_info.xml_uops_info = entry

    # Find the suitable uops info.
    instr_sched_info = json.load(istream)
    for opcode, info in instr_sched_info.items():
        xed_info = info.get('XedInfo', None)
        if xed_info is None:
            continue
        iform = xed_info['IForm']
        if iform not in iform2xml_instr_infos:
            continue

        AsmString = info['AsmString'].split('\n')[-1]
        has_same_num_opds = lambda xml_instr_info: (len(
            xml_instr_info.xml_operands_info) == len(xed_info['OpdsInfo']))
        has_same_eosz = lambda xml_instr_info: (int(
            xml_instr_info.attrib.get('eosz', -1)) == xed_info['EOSZ'])
        has_same_names = lambda xml_instr_info: ([
            x.get('name', 'UnknowName')
            for x in xml_instr_info.xml_operands_info
        ] == [x['Name'] for x in xed_info['OpdsInfo']])
        has_same_xtypes = lambda xml_instr_info: ([
            x.get('xtype', 'UnknowXType')
            for x in xml_instr_info.xml_operands_info
        ] == [x['XType'] for x in xed_info['OpdsInfo']])
        has_same_widths = lambda xml_instr_info: ([
            int(x.get('width', -1)) for x in xml_instr_info.xml_operands_info
        ] == [x['Width'] for x in xed_info['OpdsInfo']])
        has_same_zeroing = lambda xml_instr_info: (bool(
            int(xml_instr_info.attrib.get('zeroing', 0))) ==
                                                   ('{z}' in AsmString))
        has_same_mask = lambda xml_instr_info: (bool(
            int(xml_instr_info.attrib.get('mask', 0))) == bool(
                re.search(r'{%k[0-7]}', AsmString)))
        has_same_sae = lambda xml_instr_info: (bool(
            int(xml_instr_info.attrib.get('sae', 0))) == bool(
                re.search(r'{(r(n|d|u|z)-)?sae}', AsmString)))
        has_same_roundc = lambda xml_instr_info: (bool(
            int(xml_instr_info.attrib.get('roundc', 0))) == bool(
                re.search(r'{r(n|d|u|z)-sae}', AsmString)))
        no_imm_zero = lambda xml_instr_info: (int(
            xml_instr_info.attrib.get('immzero', 0)) == 0)

        def has_same_bcst(xml_instr_info):
            xml_match = re.search(r'_(\d+to\d+)',
                                  xml_instr_info.attrib['string'])
            asm_match = re.search(r'{(\d+to\d+)}', AsmString)
            if xml_match == asm_match:
                return True
            if xml_match is None or asm_match is None:
                return False
            return xml_match.group(1) == asm_match.group(1)

        # High priority comes first.
        sort_key = lambda xml_instr_info: (
            no_imm_zero(xml_instr_info),
            has_same_eosz(xml_instr_info),
            has_same_zeroing(xml_instr_info),
            has_same_mask(xml_instr_info),
            has_same_sae(xml_instr_info),
            has_same_roundc(xml_instr_info),
            has_same_bcst(xml_instr_info),
            has_same_xtypes(xml_instr_info),
            has_same_widths(xml_instr_info),
            has_same_num_opds(xml_instr_info),
            has_same_names(xml_instr_info),
        )
        iform2xml_instr_infos[iform].sort(key=sort_key, reverse=True)

        if args.debug:
            print(opcode, '-' * 80)
            for xml_instr_info in iform2xml_instr_infos[iform]:
                print(xml_instr_info.attrib)
                print(xml_instr_info.xml_uops_info)
                for opi in xml_instr_info.xml_operands_info:
                    print(' ', opi)
                print('')

        sig_name = f'uops.info.{args.arch_name}'
        uops_info = iform2xml_instr_infos[iform][0].xml_uops_info
        if uops_info is not None:
            for key, value in uops_info.items():
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
