import re

try:
    import utils
except ModuleNotFoundError:
    import lib.utils as utils


class Singleton(type):
    '''
	Each subclass should implement get_key static method to hash a uniq id
	for args passed to init and shouldn't use _instances as attr.
    '''
    def __new__(meta_cls, class_name, base_classes, attrs):
        attrs['_instances'] = {}
        cls = super().__new__(meta_cls, class_name, base_classes, attrs)

        # Create get static method for all subclasses.
        def get(*args, **kwargs):
            key = cls.get_key(*args, **kwargs)
            return cls._instances.get(key)

        cls.get = get
        return cls

    def __call__(cls, *arg, **kwargs):
        key = cls.get_key(*arg, **kwargs)
        if key not in cls._instances:
            cls._instances[key] = super().__call__(*arg, **kwargs)
        return cls._instances[key]


class ReadOnly:
    def __set_name__(self, owner, name):
        self.private_name = '_' + name

    def __get__(self, obj, objtype=None):
        return getattr(obj, self.private_name)

    def __set__(self, obj, value):
        raise TypeError("Can't assign to read only type.")


class Resource(metaclass=Singleton):
    pass


class Port(Resource):
    def __init__(self, number):
        assert isinstance(number, int), 'Expect int type'
        self._number = number

    @staticmethod
    def get_key(number):
        return number

    def __lt__(self, other):
        return self._number < other._number

    def __str__(self):
        return f'{self._number}'

    def __repr__(self):
        return self.__str__()

    @staticmethod
    def gets(nums):
        return tuple(Port(num) for num in nums)

    class GetInvalidPort:
        def __get__(self, obj, objtype=None):
            assert objtype is Port
            return objtype(-1)

    INVALID_PORT = GetInvalidPort()


class Uop:
    ''' Port, latency and throughput info for micro-op '''
    def __init__(self, ports, latency=None, throughput=None):
        assert len(ports) > 0
        assert latency is None or isinstance(latency, int)
        assert throughput is None or isinstance(throughput, float)
        self.ports = tuple(sorted(ports))
        self.latency = latency
        self.throughput = throughput

    @staticmethod
    def get_key(ports, latency=None, throughput=None):
        return (tuple(sorted(ports)), latency, throughput)

    def __repr__(self):
        return str(self.ports)

    def __lt__(self, other):
        if self.ports != other.ports:
            return self.ports < other.ports
        if self.latency != other.latency:
            return utils.lt_none(self.latency, other.latency)
        if self.throughput != other.throughput:
            return utils.lt_none(self.throughput, other.throughput)
        return False


class UopsInfo:
    ''' Uops info for instruction.  '''
    def __init__(self, latency, throughput, uops, num_uops):
        assert all(x is not None for x in (latency, uops, num_uops))
        assert isinstance(latency, int)
        assert isinstance(throughput, (type(None), float))
        self.latency = latency
        self.throughput = throughput
        self.uops = tuple(sorted(uops))
        self.num_uops = num_uops

    @property
    def ports(self):
        return tuple(uop.ports for uop in self.uops)

    @staticmethod
    def get_key(latency, throughput, uops):
        return (latency, throughput, tuple(sorted(uops)))

    def __lt__(self, other):
        if self.latency != other.latency:
            return self.latency < other.latency
        if self.throughput != other.throughput:
            return self.throughput < other.throughput
        if len(self.uops) != len(other.uops):
            return len(self.uops) < len(other.uops)
        if self.uops != other.uops:
            for uop_a, uop_b in zip(self.uops, other.uops):
                if uop_a != uop_b:
                    return uop_a < uop_b
        return False

    def __repr__(self):
        return (f'\n'
                f'    latency     = {self.latency}\n'
                f'    throughput  = {self.throughput}\n'
                f'    num_uops    = {self.num_uops}\n'
                f'    uops        = {self.uops}\n')

    def __str__(self):
        return self.__repr__()


class SchedWrite(metaclass=Singleton):
    def __init__(self, name):
        self.name = name
        self.__is_support = True

        # Each instruction may associate with many schedwrites. schedwrite that
        # is removeable for all instructions are considered to be aux schedwrite.
        # Currenty, each instruction only have 1 non aux schedwrite.
        # For simplicity, we can manually define aux schedwrite so that only 1
        # schedwrite need to be infered.
        self.__is_aux = False

    def set_resources(self,
                      resources,
                      resource_cycles,
                      latency,
                      num_uops,
                      is_aux=False):
        assert len(resources) == len(resource_cycles)
        assert all(x is not None
                   for x in (resources, resource_cycles, latency, num_uops))
        assert num_uops >= 0 and latency >= 0
        self.resources = tuple(resources)
        self.resource_cycles = tuple(resource_cycles)
        self.latency = latency
        self.num_uops = num_uops
        self.__is_aux = is_aux

    def set_supported(self, value):
        self.__is_support = value

    def is_supported(self):
        return self.__is_support

    def is_aux(self):
        return self.__is_aux

    @staticmethod
    def get_key(name):
        return name

    def get_all():
        ''' Get all schedwrites created so far.  '''
        return tuple(SchedWrite._instances.values())

    def is_complete(self):
        return all(
            hasattr(self, attr) for attr in
            ['resources', 'resource_cycles', 'latency', 'num_uops'])

    def __str__(self):
        return f'{self.name}'

    def __repr__(self):
        return self.__str__()

    def __hash__(self):
        return hash(self.name)

    def __lt__(self, other):
        # Basic class comes first.
        if type(other) is not type(self):
            return issubclass(type(other), type(self))
        return self.name < other.name


class WriteSequence(SchedWrite):
    def __init__(self, name, writes, repeat):
        super().__init__(name)
        self._writes = writes
        self._repeat = repeat
        assert not (hasattr(self, '__is_support') or hasattr(self, '__is_aux'))

    @staticmethod
    def get_key(name, writes, repeat):
        return name

    def is_complete(self):
        return all(x.is_complete() for x in self._writes)

    def is_supported(self):
        return all(x.is_supported() for x in self._writes)

    def is_aux(self):
        return all(x.is_aux() for x in self.expand())

    def set_resources(self, *args, **kwargs):
        raise TypeError('Cant set_resources on WriteSequence')

    @property
    def latency(self):
        return sum(leaf_write.latency for leaf_write in self.expand())

    @property
    def num_uops(self):
        return sum(leaf_write.num_uops for leaf_write in self.expand())

    @property
    def resources(self):
        resources = []
        for leaf_write in self.expand():
            resources.extend(leaf_write.resources)
        return tuple(resources)

    def expand(self):
        '''
        Expand WriteSequence to leaf schedwrites.
        '''
        leaf_writes = []
        for i in range(self._repeat):
            for sub_write in self._writes:
                if type(sub_write) is WriteSequence:
                    leaf_writes.extend(sub_write.expand())
                else:
                    leaf_writes.append(sub_write)
        return leaf_writes

    def __str__(self):
        return f'{self.name} writes:{self._writes} repeat:{self._repeat}'

    def __repr__(self):
        return self.__str__()


class SchedWriteRes(SchedWrite):
    def __init__(self,
                 resources,
                 resource_cycles,
                 latency,
                 num_uops,
                 prefix=""):
        # prefix will be ignored if SchedWriteRes with same resources existed.
        name = f'{prefix}WriteResGroup{len(SchedWriteRes._instances)}'
        super().__init__(name)
        self.set_resources(resources=resources,
                           resource_cycles=resource_cycles,
                           latency=latency,
                           num_uops=num_uops)

    def is_supported(self):
        return True

    def is_aux(self):
        return False

    @staticmethod
    def get_key(resources, resource_cycles, latency, num_uops, prefix):
        return (resources, resource_cycles, latency, num_uops)

    def __lt__(self, other):
        if type(other) is not type(self):
            return super().__lt__(other)

        idx0 = int(re.match(r'^\w+WriteResGroup(\d+)', self.name).group(1))
        idx1 = int(re.match(r'^\w+WriteResGroup(\d+)', other.name).group(1))
        assert idx0 != idx1, 'duplicate SchedWriteRes'
        return idx0 < idx1


class SchedRead(metaclass=Singleton):
    def __init__(self, name: str):
        self.name = name

    @staticmethod
    def get_key(name):
        return name

    def __str__(self):
        return f'{self.name}'

    def __repr__(self):
        return self.__str__()


class LLVMInstr:
    ''' Instruction defined in td file '''
    def __init__(self, opcode, schedreads, schedwrites, isa_set):
        self.opcode = opcode
        self.schedreads = schedreads
        self.schedwrites = schedwrites
        self.isa_set = isa_set
        self._use_instrw = False

    def set_uops_info(self, uops_info):
        self.uops_info = uops_info

    def set_use_instrw(self, value):
        self._use_instrw = value

    def use_instrw(self):
        return self._use_instrw

    def has_uops_info(self):
        return hasattr(self, 'uops_info')

    def is_invalid(self, target_cpu):
        return (self.isa_set is not None
                and self.isa_set not in target_cpu.valid_isa_set)

    def replace_or_add_schedrw(self,
                               old_schedrw,
                               new_schedrw,
                               is_read=False,
                               *,
                               not_null=False):
        schedrws = self.schedreads if is_read else self.schedwrites
        if not not_null and old_schedrw is None:
            schedrws.append(new_schedrw)
        else:
            schedrws[schedrws.index(old_schedrw)] = new_schedrw

    def compute_latency(self):
        return max(schedwrite.latency for schedwrite in self.schedwrites)

    def compute_num_uops(self):
        return sum(schedwrite.num_uops for schedwrite in self.schedwrites)

    def compute_resources(self):
        resources = []
        for schedwrite in self.schedwrites:
            resources.extend(schedwrite.resources)
        return tuple(resources)

    def __repr__(self):
        return (f'{self.opcode}:\n'
                f'  schedreads  = {self.schedreads}\n'
                f'  schedwrites = {self.schedwrites}\n'
                f'  isa_set     = {self.isa_set}\n'
                f'  use_instrw  = {self._use_instrw}\n'
                f'  uops_info   = {getattr(self, "uops_info", None)}\n')

    def __str__(self):
        return self.__repr__()


class SMVInstr:
    def __init__(self, opcode, latency, num_uops, throughput, resources,
                 resource_cycles):
        self.opcode = opcode
        self.latency = latency
        self.num_uops = num_uops
        self.throughput = throughput
        self.resources = resources
        self.resource_cycles = resource_cycles

    def __repr__(self):
        return (f'{self.opcode}:\n'
                f'  latency         = {self.latency}\n'
                f'  num_uops        = {self.num_uops}\n'
                f'  throughput      = {self.throughput}\n'
                f'  resources       = {self.resources}\n'
                f'  resource_cycles = {self.resource_cycles}\n')
