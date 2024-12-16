import collections, os, re, unittest


def to_int(obj, base=10):
    if isinstance(obj, int):
        return obj
    try:
        return int(obj, base)
    except:
        return None


def nums2str(nums, width, sep='', prefix=''):
    formated_nums = [str(int(num)).zfill(width) for num in nums]
    return prefix + sep.join(formated_nums)


def str2nums(string, sep='', prefix=''):
    formated_nums = string.lstrip(prefix).split(sep)
    return [int(num) for num in formated_nums]


def listremove(a, b):
    ''' Return "a - b". '''
    ac = list(a)
    for i in b:
        ac.remove(i)
    return type(a)(ac)


def listdiff(a, b):
    check = True
    ac, bc = list(a), list(b)
    while check:
        check = False
        for x in ac:
            if x in bc:
                ac.remove(x)
                bc.remove(x)
                check = True
                break
    return tuple(ac + bc)


def listcontain(a, b):
    '''
    Return true is b is subset of a.
    '''
    ac = list(a)
    for x in b:
        if x in ac:
            ac.remove(x)
        else:
            return False
    return True


def lt_none(a, b):
    if (a is None and b is None) or a is None:
        return True
    elif b is None:
        return False
    else:
        return a < b


def cmplist(a, b):
    return collections.Counter(a) == collections.Counter(b)


def commonpostfix(strings):
    inversed_strings = [string[::-1] for string in strings.copy()]
    inversed_common_postfix = os.path.commonprefix(inversed_strings)
    return inversed_common_postfix[::-1]


class RegexReducer:
    ''' Reduce a list of regexes to more concise regexes. '''
    def __init__(self, diff_len_limit=2):

        # Determin what len of non-number diff are allowed.
        # 0 means only digits diff are allowed.
        # 1 means only 1 non-digits diff are allowed.
        self.diff_len_limit = diff_len_limit

    def __is_all_digits(self, diff1, diff2):
        return diff1.isdigit() and diff2.isdigit()

    def __is_under_limit(self, diff1, diff2):
        return max(len(diff1), len(diff2)) <= self.diff_len_limit

    def __is_in_regex(self, string, begin, end):
        probe = 0
        for i in range(end):
            if string[i] == '(':
                probe += 1
            elif string[i] == ')':
                probe -= 1

            if i >= begin and i < end and (probe != 0 or string[i] == '?'):
                return True
        return False

    def reduce_once(self, regexes_in):
        assert isinstance(regexes_in, list), 'list type is required'

        changed = False
        worklist, regexes_out = regexes_in.copy()[::-1], []
        while worklist:
            specimen = worklist.pop()
            common_prefix, common_postfix, members = None, None, []

            # Ascending priority. If diff are pure numbers, allow it. If not,
            # check if diff len is under limit.
            checker_list = [self.__is_under_limit, self.__is_all_digits]

            # Step1: find a pair of common_prefix/postfix meets requirment.
            while (checker_list
                   and (common_prefix, common_postfix) == (None, None)):
                checker = checker_list.pop()
                for string in worklist:
                    cprefix = os.path.commonprefix([string, specimen])

                    # get postfix for the rest part.
                    cpostfix = commonpostfix(
                        [string[len(cprefix):], specimen[len(cprefix):]])

                    # [begin, end) index of diff1/diff2.
                    begin1, end1 = len(cprefix), len(specimen) - len(cpostfix)
                    begin2, end2 = len(cprefix), len(string) - len(cpostfix)

                    diff1, diff2 = specimen[begin1:end1], string[begin2:end2]

                    if ((not self.__is_in_regex(specimen, begin1, end1))
                            and (not self.__is_in_regex(string, begin2, end2))
                            and checker(diff1, diff2)):
                        common_prefix, common_postfix = cprefix, cpostfix
                        changed = True
                        break

            # Step2: find members of this common_prefix/postfix.
            if (common_prefix, common_postfix) != (None, None):
                for string in worklist:
                    cprefix = os.path.commonprefix([string, specimen])
                    cpostfix = commonpostfix(
                        [string[len(cprefix):], specimen[len(cprefix):]])
                    begin1, end1 = len(cprefix), len(specimen) - len(cpostfix)
                    begin2, end2 = len(cprefix), len(string) - len(cpostfix)
                    diff1, diff2 = specimen[begin1:end1], string[begin2:end2]

                    if ((common_prefix, common_postfix) == (cprefix, cpostfix)
                            and checker(diff1, diff2)):
                        members.append(string)

            # Step3: remove members from worklist.
            for member in members:
                worklist.remove(member)
            members.append(specimen)

            # Step4: gen regex for members.
            if len(members) == 1:
                regex = members[0]
            else:
                diffs = [
                    x[len(common_prefix):len(x) - len(common_postfix)]
                    for x in members
                ]
                need_question_mark = False
                if '' in diffs:
                    need_question_mark = True
                    diffs = [x for x in diffs if x != '']
                if diffs:
                    diffs.sort(key=lambda x: (len(x), x))
                    regex = '|'.join(diffs)
                    if len(diffs) > 1 or len(diffs[0]) > 1:
                        regex = '(' + regex + ')'
                if need_question_mark:
                    regex = f'({regex}?)'
                regex = common_prefix + regex + common_postfix

            regexes_out.append(regex)

        if changed:
            assert (set(regexes_out) != set(regexes_in))
        return (regexes_out, changed)

    def reduce(self, regexes_in):
        changed = True
        last_regexes = regexes_in

        # Wordaround to prefer short prefix.
        real_limit = self.diff_len_limit
        if real_limit > 2:
            self.diff_len_limit = 2
            while changed:
                last_regexes, changed = self.reduce_once(last_regexes)
            self.diff_len_limit = real_limit
            changed = True

        while changed:
            last_regexes, changed = self.reduce_once(last_regexes)

        # Validation.
        for regex_in in regexes_in:
            hit = 0
            for regex_out in last_regexes:
                if re.match(f'^{regex_out}$', regex_in):
                    hit += 1
            assert hit == 1, f'{regex_in}, {regexes_in}'

        return last_regexes


if __name__ == '__main__':

    class UtilsChecker(unittest.TestCase):
        def test_to_int(self):
            self.assertEqual(to_int('1a'), None)
            self.assertEqual(to_int('0x12', 16), 0x12)
            self.assertEqual(to_int(4), 4)
            self.assertEqual(to_int('12'), 12)

        def test_nums2str(self):
            self.assertEqual(nums2str([1, 2, 3], 2, sep='_', prefix='GRTPort'),
                             'GRTPort01_02_03')

        def test_str2nums(self):
            self.assertEqual(
                str2nums('GRTPort01_02_03', sep='_', prefix='GRTPort'),
                [1, 2, 3])

        def test_listdiff(self):
            self.assertEqual(listdiff([1, 1, 2], [3, 2, 4, 2, 1]),
                             (1, 3, 4, 2))

        def test_listremove(self):
            self.assertEqual(listremove([1, 1, 2], [1]), [1, 2])

        def test_listcontain(self):
            self.assertTrue(listcontain([1, 1, 2], [1]))
            self.assertFalse(listcontain([1, 1, 2], [3]))

        def test_regex_reducer(self):
            self.assertEqual(
                RegexReducer().reduce([
                    'ABS8ri8', 'ABS16ri8', 'ABS8mr', 'ABS32ri16', 'ABS32ri32',
                    'ABS8x', 'ABS8f', 'ABS8i', 'ABS8', 'aes'
                ]),
                ['ABS(8|16)ri8', 'ABS8((f|i|x|mr)?)', 'ABS32ri(16|32)', 'aes'])
            self.assertEqual(
                RegexReducer(1).reduce([
                    'ABS8ri8', 'ABS16ri8', 'ABS8mr', 'ABS32ri16', 'ABS32ri32',
                    'ABS8x', 'ABS8f', 'ABS8i', 'ABS8', 'aes'
                ]), [
                    'ABS(8|16)ri8', 'ABS8mr', 'ABS32ri(16|32)',
                    'ABS8((f|i|x)?)', 'aes'
                ])
            self.assertEqual(
                RegexReducer(0).reduce([
                    'ABS8ri8', 'ABS16ri8', 'ABS8mr', 'ABS32ri16', 'ABS32ri32',
                    'ABS8x', 'ABS8f', 'ABS8i', 'ABS8', 'aes'
                ]), [
                    'ABS(8|16)ri8', 'ABS8mr', 'ABS32ri(16|32)', 'ABS8x',
                    'ABS8f', 'ABS8i', 'ABS8', 'aes'
                ])
            self.assertEqual(
                RegexReducer().reduce_once(
                    ['(V?)CVTTSS2SI64rr_Int', '(V?)CVTSS2SI64rr_Int'])[0],
                ['(V?)CVT(T?)SS2SI64rr_Int'])
            self.assertEqual(
                RegexReducer(4).reduce([
                    'CVTSD2SIrm', 'CVTSD2SIrm_Int', 'VCVTSD2SIrm',
                    'VCVTSD2SIrm_Int', 'CVTTSD2SIrm', 'CVTTSD2SIrm_Int',
                    'VCVTTSD2SIrm_Int', 'VCVTTSD2SIrm'
                ]), ['(V?)CVT(T?)SD2SIrm((_Int)?)'])

    unittest.main()
