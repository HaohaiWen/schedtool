import os, unittest

try:
    import utils
    from llvm_instr import Port, SchedWrite
except ModuleNotFoundError:
    from lib import utils
    from lib.llvm_instr import Port, SchedWrite

workdir = f'{os.path.dirname(os.path.realpath(__file__))}'


def get_target(target_cpu):
    target_map = {
        'alderlake-p': AlderlakeP,
        'sapphirerapids': SapphireRapids,
        'skylake': Skylake,
        'skylake-avx512': SkylakeServer,
        'icelake-server': IcelakeServer,
    }
    if target_cpu not in target_map:
        raise NotImplementedError(f'Unknown target cpu "{target_cpu}"\n'
                                  f'Valid target is {list(target_map.keys())}')
    return target_map[target_cpu]()


class TargetCPU:
    def __init__(self, short_name, proc_name, model_name=None):
        self.short_name = short_name
        self.proc_name = proc_name
        self.model_name = f'{proc_name.capitalize()}Model' \
                          if model_name is None else model_name
        self.all_ports = None

    def get_ports_name(self, ports):
        if len(ports) == 0:
            return ''

        if utils.cmplist(ports, self.all_ports):
            return f'{self.short_name}PortAny'

        if utils.cmplist(ports, (Port.INVALID_PORT, )):
            return f'{self.short_name}PortInvalid'

        assert all(port in self.all_ports for port in ports)
        return utils.nums2str((str(port) for port in ports), 2, '_',
                              f'{self.short_name}Port')

    def parse_ports_name(self, ports_name: str):
        ''' Convert ports name to Port.  '''
        if ports_name == f'{self.short_name}PortAny':
            return self.all_ports

        if ports_name == f'{self.short_name}PortInvalid':
            return (Port.INVALID_PORT, )

        ports = []
        for num in utils.str2nums(ports_name, '_', f'{self.short_name}Port'):
            assert Port(num) in self.all_ports
            ports.append(Port(num))
        return tuple(ports)

    def lat2str(self, latency):
        if latency == self.max_latency:
            return f'{self.model_name}.MaxLatency'
        else:
            return str(latency)


class AlderlakeP(TargetCPU):
    valid_isa_set = frozenset('''
        3DNOW_PREFETCH  ADOX_ADCX AES AVX
        AVX2  AVX2GATHER  AVXAES  AVX_GFNI
        AVX_VNNI  BMI1  BMI2  CET
        CLDEMOTE  CLFLUSHOPT  CLFSH CLWB
        CMOV  CMPXCHG16B  F16C  FAT_NOP
        FCMOV FMA FXSAVE  FXSAVE64
        GFNI  HRESET  I186  I286PROTECTED
        I286REAL  I386  I486  I486REAL
        I86 INVPCID KEYLOCKER KEYLOCKER_WIDE
        LAHF  LONGMODE  LZCNT MONITOR
        MOVBE MOVDIR  PAUSE PCLMULQDQ
        PCONFIG PENTIUMMMX  PENTIUMREAL PKU
        POPCNT  PPRO  PPRO_UD0_SHORT  PREFETCHW
        PREFETCH_NOP  PTWRITE RDPID RDPMC
        RDRAND  RDSEED  RDTSCP  RDWRFSGS
        SERIALIZE SHA SMAP  SMX
        SSE SSE2  SSE2MMX SSE3
        SSE3X87 SSE4  SSE42 SSEMXCSR
        SSE_PREFETCH  SSSE3 SSSE3MMX  VAES
        VMFUNC  VPCLMULQDQ  VTX WAITPKG
        WBNOINVD  X87 XSAVE XSAVEC
        XSAVEOPT  XSAVES
        '''.split())

    def __init__(self):
        super().__init__('ADLP', 'alderlake', 'AlderlakePModel')
        self.all_ports = tuple(
            Port(num) for num in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11))
        self.load_ports = Port.gets((2, 3, 11))
        self.load_latency = 5
        self.max_latency = 100
        self.template_td = f'{workdir}/template/alderlake-p.td'

        # Manually set some schedwrites resources instead of infering it.
        self.__set_schedwrite_resource()

    def __set_schedwrite_resource(self):
        ADLPPort04_09 = Port.gets((4, 9))
        ADLPPort07_08 = Port.gets((7, 8))

        # Manually define aux SchedWrite here.
        SchedWrite('WriteIMulH').set_resources(resources=(),
                                               resource_cycles=(),
                                               latency=3,
                                               num_uops=1,
                                               is_aux=True)
        SchedWrite('WriteIMulHLd').set_resources(resources=(),
                                                 resource_cycles=(),
                                                 latency=3,
                                                 num_uops=1,
                                                 is_aux=True)
        SchedWrite('WriteRMW').set_resources(resources=(self.load_ports,
                                                        ADLPPort04_09,
                                                        ADLPPort07_08),
                                             resource_cycles=(1, 1, 1),
                                             latency=1,
                                             num_uops=3,
                                             is_aux=True)
        SchedWrite('WriteVecMaskedGatherWriteback').set_resources(
            resources=(),
            resource_cycles=(),
            latency=self.load_latency,
            num_uops=0,
            is_aux=True)

        # Manually define non-aux SchedWrite here.
        SchedWrite('WriteZero').set_resources(resources=(),
                                              resource_cycles=(),
                                              latency=1,
                                              num_uops=1)
        SchedWrite('WriteLoad').set_resources(resources=(self.load_ports, ),
                                              resource_cycles=(1, ),
                                              latency=self.load_latency,
                                              num_uops=1)


class SapphireRapids(TargetCPU):
    valid_isa_set = frozenset('''
        3DNOW_PREFETCH  ADOX_ADCX AES AMX_BF16
        AMX_INT8  AMX_TILE  AVX AVX2
        AVX2GATHER  AVX512BW_128  AVX512BW_128N AVX512BW_256
        AVX512BW_512  AVX512BW_KOP  AVX512CD_128  AVX512CD_256
        AVX512CD_512  AVX512DQ_128  AVX512DQ_128N AVX512DQ_256
        AVX512DQ_512  AVX512DQ_KOP  AVX512DQ_SCALAR AVX512F_128
        AVX512F_128N  AVX512F_256 AVX512F_512 AVX512F_KOP
        AVX512F_SCALAR  AVX512_BF16_128 AVX512_BF16_256 AVX512_BF16_512
        AVX512_BITALG_128 AVX512_BITALG_256 AVX512_BITALG_512 AVX512_FP16_128
        AVX512_FP16_128N  AVX512_FP16_256 AVX512_FP16_512 AVX512_FP16_SCALAR
        AVX512_GFNI_128 AVX512_GFNI_256 AVX512_GFNI_512 AVX512_IFMA_128
        AVX512_IFMA_256 AVX512_IFMA_512 AVX512_VAES_128 AVX512_VAES_256
        AVX512_VAES_512 AVX512_VBMI2_128  AVX512_VBMI2_256  AVX512_VBMI2_512
        AVX512_VBMI_128 AVX512_VBMI_256 AVX512_VBMI_512 AVX512_VNNI_128
        AVX512_VNNI_256 AVX512_VNNI_512 AVX512_VP2INTERSECT_128
        AVX512_VP2INTERSECT_256 AVX512_VP2INTERSECT_512 AVX512_VPCLMULQDQ_128
        AVX512_VPCLMULQDQ_256 AVX512_VPCLMULQDQ_512 AVX512_VPOPCNTDQ_128
        AVX512_VPOPCNTDQ_256  AVX512_VPOPCNTDQ_512  AVXAES
        AVX_GFNI  AVX_VNNI  BMI1  BMI2
        CET CLDEMOTE  CLFLUSHOPT  CLFSH
        CLWB  CMOV  CMPXCHG16B  ENQCMD
        F16C  FAT_NOP FCMOV FMA
        FXSAVE  FXSAVE64  GFNI  I186
        I286PROTECTED I286REAL  I386  I486
        I486REAL  I86 INVPCID LAHF
        LONGMODE  LZCNT MONITOR MOVBE
        MOVDIR  PAUSE PCLMULQDQ PCONFIG
        PENTIUMMMX  PENTIUMREAL PKU POPCNT
        PPRO  PPRO_UD0_LONG PREFETCHW PREFETCH_NOP
        PTWRITE RDPID RDPMC RDRAND
        RDSEED  RDTSCP  RDWRFSGS  RTM
        SERIALIZE SGX SGX_ENCLV SHA
        SMAP  SMX SSE SSE2
        SSE2MMX SSE3  SSE3X87 SSE4
        SSE42 SSEMXCSR  SSE_PREFETCH  SSSE3
        SSSE3MMX  TDX TSX_LDTRK UINTR
        VAES  VMFUNC  VPCLMULQDQ  VTX
        WAITPKG WBNOINVD  X87 XSAVE
        XSAVEC  XSAVEOPT  XSAVES
        '''.split())

    def __init__(self):
        super().__init__('SPR', 'sapphirerapids', 'SapphireRapidsModel')
        self.all_ports = tuple(
            Port(num) for num in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11))
        self.load_ports = Port.gets((2, 3, 11))
        self.load_latency = 5
        self.max_latency = 100
        self.template_td = f'{workdir}/template/sapphirerapids.td'

        # Manually set some schedwrites resources instead of infering it.
        self.__set_schedwrite_resource()

    def __set_schedwrite_resource(self):
        SPRPort04_09 = Port.gets((4, 9))
        SPRPort07_08 = Port.gets((7, 8))
        SPRPort00_06 = Port.gets((0, 6))

        # Manually define aux SchedWrite here.
        SchedWrite('WriteIMulH').set_resources(resources=(),
                                               resource_cycles=(),
                                               latency=3,
                                               num_uops=1,
                                               is_aux=True)
        SchedWrite('WriteIMulHLd').set_resources(resources=(),
                                                 resource_cycles=(),
                                                 latency=3,
                                                 num_uops=1,
                                                 is_aux=True)
        SchedWrite('WriteRMW').set_resources(resources=(self.load_ports,
                                                        SPRPort04_09,
                                                        SPRPort07_08),
                                             resource_cycles=(1, 1, 1),
                                             latency=1,
                                             num_uops=3,
                                             is_aux=True)
        SchedWrite('WriteVecMaskedGatherWriteback').set_resources(
            resources=(),
            resource_cycles=(),
            latency=self.load_latency,
            num_uops=0,
            is_aux=True)

        # Manually define non-aux SchedWrite here.
        SchedWrite('WriteZero').set_resources(resources=(),
                                              resource_cycles=(),
                                              latency=1,
                                              num_uops=1)
        SchedWrite('WriteLoad').set_resources(resources=(self.load_ports, ),
                                              resource_cycles=(1, ),
                                              latency=self.load_latency,
                                              num_uops=1)
        SchedWrite('WriteCMOV').set_resources(resources=(SPRPort00_06, ),
                                              resource_cycles=(1, ),
                                              latency=1,
                                              num_uops=1)


class Skylake(TargetCPU):
    valid_isa_set = frozenset('''
        3DNOW_PREFETCH  ADOX_ADCX AES AVX
        AVX2  AVX2GATHER  AVXAES  BMI1
        BMI2  CLFLUSHOPT  CLFSH CMOV
        CMPXCHG16B  F16C  FAT_NOP FCMOV
        FMA FXSAVE  FXSAVE64  I186
        I286PROTECTED I286REAL  I386  I486
        I486REAL  I86 INVPCID LAHF
        LONGMODE  LZCNT MONITOR MOVBE
        MPX PAUSE PCLMULQDQ PENTIUMMMX
        PENTIUMREAL POPCNT  PPRO  PPRO_UD0_LONG
        PREFETCHW PREFETCH_NOP  RDPMC RDRAND
        RDSEED  RDTSCP  RDWRFSGS  RTM
        SGX SMAP  SMX SSE
        SSE2  SSE2MMX SSE3  SSE3X87
        SSE4  SSE42 SSEMXCSR  SSE_PREFETCH
        SSSE3 SSSE3MMX  VMFUNC  VTX
        X87 XSAVE XSAVEC  XSAVEOPT
        XSAVES
        '''.split())

    def __init__(self):
        super().__init__('SKL', 'skylake')
        self.all_ports = tuple(Port(num) for num in (0, 1, 2, 3, 4, 5, 6, 7))
        self.load_ports = Port.gets((2, 3))
        self.load_latency = 5
        self.max_latency = 100

    def parse_ports_name(self, ports_name: str):
        ''' Convert ports name to Port.  '''
        if ports_name == f'{self.short_name}PortAny':
            return self.all_ports

        if ports_name in (f'{self.short_name}Divider',
                          f'{self.short_name}FPDivider'):
            return (Port.INVALID_PORT, )

        ports = []
        for num in ports_name[len(f'{self.short_name}Port'):]:
            num = int(num)
            assert Port(num) in self.all_ports
            ports.append(Port(num))
        return tuple(ports)


class SkylakeServer(TargetCPU):
    valid_isa_set = frozenset('''
        3DNOW_PREFETCH  ADOX_ADCX AES AVX
        AVX2  AVX2GATHER  AVX512BW_128  AVX512BW_128N
        AVX512BW_256  AVX512BW_512  AVX512BW_KOP  AVX512CD_128
        AVX512CD_256  AVX512CD_512  AVX512DQ_128  AVX512DQ_128N
        AVX512DQ_256  AVX512DQ_512  AVX512DQ_KOP  AVX512DQ_SCALAR
        AVX512F_128 AVX512F_128N  AVX512F_256 AVX512F_512
        AVX512F_KOP AVX512F_SCALAR  AVXAES  BMI1
        BMI2  CLFLUSHOPT  CLFSH CLWB
        CMOV  CMPXCHG16B  F16C  FAT_NOP
        FCMOV FMA FXSAVE  FXSAVE64
        I186  I286PROTECTED I286REAL  I386
        I486  I486REAL  I86 INVPCID
        LAHF  LONGMODE  LZCNT MONITOR
        MOVBE MPX PAUSE PCLMULQDQ
        PENTIUMMMX  PENTIUMREAL PKU POPCNT
        PPRO  PPRO_UD0_LONG PREFETCHW PREFETCH_NOP
        RDPMC RDRAND  RDSEED  RDTSCP
        RDWRFSGS  RTM SGX SMAP
        SMX SSE SSE2  SSE2MMX
        SSE3  SSE3X87 SSE4  SSE42
        SSEMXCSR  SSE_PREFETCH  SSSE3 SSSE3MMX
        VMFUNC  VTX X87 XSAVE
        XSAVEC  XSAVEOPT  XSAVES
        '''.split())

    def __init__(self):
        super().__init__('SKX', 'skylake-avx512')
        self.all_ports = tuple(Port(num) for num in (0, 1, 2, 3, 4, 5, 6, 7))
        self.load_ports = Port.gets((2, 3))
        self.load_latency = 5
        self.max_latency = 100

    def parse_ports_name(self, ports_name: str):
        '''
        Convert ports name to Port.
        '''
        if ports_name == f'{self.short_name}PortAny':
            return self.all_ports

        if ports_name in (f'{self.short_name}Divider',
                          f'{self.short_name}FPDivider'):
            return (Port.INVALID_PORT, )

        ports = []
        for num in ports_name[len(f'{self.short_name}Port'):]:
            num = int(num)
            assert Port(num) in self.all_ports
            ports.append(Port(num))
        return tuple(ports)


class IcelakeServer(TargetCPU):
    valid_isa_set = frozenset('''
        3DNOW_PREFETCH  ADOX_ADCX AES AVX
        AVX2  AVX2GATHER  AVX512BW_128  AVX512BW_128N
        AVX512BW_256  AVX512BW_512  AVX512BW_KOP  AVX512CD_128
        AVX512CD_256  AVX512CD_512  AVX512DQ_128  AVX512DQ_128N
        AVX512DQ_256  AVX512DQ_512  AVX512DQ_KOP  AVX512DQ_SCALAR
        AVX512F_128 AVX512F_128N  AVX512F_256 AVX512F_512
        AVX512F_KOP AVX512F_SCALAR  AVX512_BITALG_128 AVX512_BITALG_256
        AVX512_BITALG_512 AVX512_GFNI_128 AVX512_GFNI_256 AVX512_GFNI_512
        AVX512_IFMA_128 AVX512_IFMA_256 AVX512_IFMA_512 AVX512_VAES_128
        AVX512_VAES_256 AVX512_VAES_512 AVX512_VBMI2_128  AVX512_VBMI2_256
        AVX512_VBMI2_512  AVX512_VBMI_128 AVX512_VBMI_256 AVX512_VBMI_512
        AVX512_VNNI_128 AVX512_VNNI_256 AVX512_VNNI_512 AVX512_VPCLMULQDQ_128
        AVX512_VPCLMULQDQ_256 AVX512_VPCLMULQDQ_512 AVX512_VPOPCNTDQ_128
        AVX512_VPOPCNTDQ_256 AVX512_VPOPCNTDQ_512  AVXAES  AVX_GFNI  BMI1
        BMI2  CLFLUSHOPT  CLFSH CLWB
        CMOV  CMPXCHG16B  F16C  FAT_NOP
        FCMOV FCOMI FMA FXSAVE
        FXSAVE64  GFNI  I186  I286PROTECTED
        I286REAL  I386  I486  I486REAL
        I86 INVPCID LAHF  LONGMODE
        LZCNT MONITOR MOVBE PAUSE
        PCLMULQDQ PCONFIG PENTIUMMMX  PENTIUMREAL
        PKU POPCNT  PPRO  PPRO_UD0_LONG
        PREFETCHW PREFETCH_NOP  RDPID RDPMC
        RDRAND  RDSEED  RDTSCP  RDWRFSGS
        RTM SGX SGX_ENCLV SHA
        SMAP  SMX SSE SSE2
        SSE2MMX SSE3  SSE3X87 SSE4
        SSE42 SSEMXCSR  SSE_PREFETCH  SSSE3
        SSSE3MMX  VAES  VMFUNC  VPCLMULQDQ
        VTX WBNOINVD  X87 XSAVE
        XSAVEC  XSAVEOPT  XSAVES
        '''.split())

    def __init__(self):
        super().__init__('ICX', 'icelake-server')
        self.all_ports = tuple(
            Port(num) for num in (0, 1, 2, 3, 4, 5, 6, 7, 8, 9))
        self.load_ports = Port.gets((2, 3))
        self.load_latency = 5
        self.max_latency = 100

    def parse_ports_name(self, ports_name: str):
        '''
        Convert ports name to Port.
        '''
        if ports_name == f'{self.short_name}PortAny':
            return self.all_ports

        if ports_name in (f'{self.short_name}Divider',
                          f'{self.short_name}FPDivider'):
            return (Port.INVALID_PORT, )

        ports = []
        for num in ports_name[len(f'{self.short_name}Port'):]:
            num = int(num)
            assert Port(num) in self.all_ports
            ports.append(Port(num))
        return tuple(ports)


if __name__ == '__main__':

    class TargetChecker(unittest.TestCase):
        def test_target(self):
            target_cpu = AlderlakeP()
            self.assertEqual(target_cpu.get_ports_name([]), '')
            self.assertEqual(target_cpu.get_ports_name([Port(1),
                                                        Port(2)]),
                             'ADLPPort01_02')
            self.assertEqual(target_cpu.get_ports_name([Port.INVALID_PORT]),
                             'ADLPPortInvalid')
            self.assertEqual(target_cpu.parse_ports_name('ADLPPort1_3'),
                             (Port(1), Port(3)))

    unittest.main()
