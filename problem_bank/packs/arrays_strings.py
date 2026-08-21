from problem_bank.schema import ProblemSpec
from problem_bank.schema import TestCase


def get_specs() -> tuple[ProblemSpec, ...]:
    return (
        ProblemSpec(
            title='Lone Number in Pairs',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='arrays and counting',
            description=(
                'You are given an odd-length array in which every number appears exactly twice '
                'except one number. Output the number that appears once.'
            ),
            input_description='The first line contains n. The second line contains n integers.',
            output_description='Print the number that appears exactly once.',
            sample_input='7\n4 9 4 9 7 2 2\n',
            sample_output='7\n',
            cases=(
                TestCase('1\n42\n', '42\n'),
                TestCase('3\n5 7 5\n', '7\n'),
                TestCase('5\n1 2 1 2 9\n', '9\n'),
                TestCase('7\n-3 8 -3 8 8 8 11\n', '11\n'),
                TestCase('7\n100 100 200 300 200 300 999\n', '999\n'),
                TestCase('9\n4 4 4 4 6 6 6 6 10\n', '10\n'),
                TestCase('11\n0 -1 0 2 -1 2 3 4 3 4 123456789\n', '123456789\n'),
                TestCase(
                    '9\n-1000000000 7 -1000000000 7 2147483647 12 12 9 9\n',
                    '2147483647\n',
                ),
                TestCase('13\n6 6 1 2 1 2 3 3 4 4 5 5 -7\n', '-7\n'),
                TestCase(
                    '15\n8 8 8 8 8 8 13 13 13 13 21 21 21 21 -999\n',
                    '-999\n',
                ),
            ),
        ),
        ProblemSpec(
            title='Longest Uniform Streak',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='strings',
            description=(
                'Given a nonempty lowercase string, find the length of its longest contiguous '
                'run consisting of one repeated character.'
            ),
            input_description='One line containing a nonempty lowercase string.',
            output_description='Print the maximum length of a uniform contiguous run.',
            sample_input='aabbbccccaa\n',
            sample_output='4\n',
            cases=(
                TestCase('a\n', '1\n'),
                TestCase('aa\n', '2\n'),
                TestCase('abacaba\n', '1\n'),
                TestCase('aabbbccccaa\n', '4\n'),
                TestCase('zzzzzyx\n', '5\n'),
                TestCase('mississippi\n', '2\n'),
                TestCase('abcdddddeffggg\n', '5\n'),
                TestCase('aaaaaaaaaa\n', '10\n'),
                TestCase('qwertyuiop\n', '1\n'),
                TestCase('xxxyyyzzzzzzww\n', '6\n'),
            ),
        ),
        ProblemSpec(
            title='Vowel-Edge Words',
            difficulty='easy',
            time_limit=1000,
            memory_limit=128,
            source='strings and parsing',
            description=(
                'Count the words whose first and last characters are the same vowel. '
                'The five vowels are a, e, i, o, and u.'
            ),
            input_description=(
                'The first token is n. It is followed by n lowercase words separated by '
                'arbitrary whitespace.'
            ),
            output_description='Print the number of words that begin and end with the same vowel.',
            sample_input='5\narea unit sky echo idea\n',
            sample_output='1\n',
            cases=(
                TestCase('1\na\n', '1\n'),
                TestCase('4\narea unit sky echo\n', '1\n'),
                TestCase('5\narea\neerie\notto\nunit\nubuntu\n', '4\n'),
                TestCase('6\napple olive image arena umbrella orange\n', '1\n'),
                TestCase('8\nalpha\nbeta\ncivic\neerie\nigloo\notto\nunit\nubuntu\n', '4\n'),
                TestCase('7\narea\tunit\n echo\nidea   otto\numbrella\nnoon\n', '2\n'),
                TestCase('10\na e i o u aa ee ii oo uu\n', '10\n'),
                TestCase('3\nrhythm myrrh crypt\n', '0\n'),
                TestCase('9\nlevel radar rotator\nmadam\nrefer\ncivic\nkayak\nnoon\ntest\n', '0\n'),
                TestCase(
                    '12\narea\narea\neerie\neerie\notto\notto\nubuntu\nubuntu\nunit\nsky\ncat\ndog\n',
                    '8\n',
                ),
            ),
        ),
        ProblemSpec(
            title='Sorted Pair Target Count',
            difficulty='medium',
            time_limit=1500,
            memory_limit=128,
            source='arrays and two pointers',
            description=(
                'Given a nondecreasing array, count the index pairs (i, j) with i < j whose '
                'values add up to the target.'
            ),
            input_description=(
                'The first line contains n and target. The second line contains n integers in '
                'nondecreasing order.'
            ),
            output_description='Print the number of index pairs whose values sum to target.',
            sample_input='8 10\n1 1 2 3 7 8 9 9\n',
            sample_output='6\n',
            cases=(
                TestCase('1 5\n5\n', '0\n'),
                TestCase('2 10\n5 5\n', '1\n'),
                TestCase('4 6\n1 2 3 5\n', '1\n'),
                TestCase('6 10\n1 1 2 3 7 9\n', '3\n'),
                TestCase('8 10\n1 1 2 3 7 8 9 9\n', '6\n'),
                TestCase('6 10\n5 5 5 5 5 5\n', '15\n'),
                TestCase('7 -2\n-5 -3 -2 0 1 2 4\n', '2\n'),
                TestCase('5 100\n1 2 3 4 5\n', '0\n'),
                TestCase('10 0\n-5 -5 -5 -1 0 1 5 5 5 9\n', '10\n'),
                TestCase('12 20\n0 2 2 4 6 8 12 14 16 18 18 20\n', '8\n'),
            ),
        ),
        ProblemSpec(
            title='Smallest Pattern Window',
            difficulty='medium',
            time_limit=2000,
            memory_limit=128,
            source='strings and sliding windows',
            description=(
                'Find the length of the shortest contiguous substring of source that contains '
                'every character of pattern with at least the required multiplicity.'
            ),
            input_description='The first line contains source and the second line contains pattern.',
            output_description=(
                'Print the shortest window length, or -1 if no window contains the pattern.'
            ),
            sample_input='adobecodebanc\nabc\n',
            sample_output='4\n',
            cases=(
                TestCase('a\na\n', '1\n'),
                TestCase('abc\nz\n', '-1\n'),
                TestCase('abca\nac\n', '2\n'),
                TestCase('adobecodebanc\nabc\n', '4\n'),
                TestCase('aaabbb\nab\n', '2\n'),
                TestCase('aabbccbb\nbbc\n', '3\n'),
                TestCase('abcdebdde\nbce\n', '4\n'),
                TestCase('xyzxyz\nzzx\n', '4\n'),
                TestCase('bbac\nbb\n', '2\n'),
                TestCase('abcdefghijklmnopqrstuvwxyzabcdefghijklmnopqrstuvwxyz\naz\n', '2\n'),
            ),
        ),
        ProblemSpec(
            title='Balance Index',
            difficulty='medium',
            time_limit=1500,
            memory_limit=128,
            source='arrays and prefix sums',
            description=(
                'Find the first 1-based index whose left-side sum equals its right-side sum. '
                'The value at the index is excluded from both sums.'
            ),
            input_description='The first line contains n. The second line contains n integers.',
            output_description='Print the first balance index, or -1 if no such index exists.',
            sample_input='7\n1 2 3 6 3 2 1\n',
            sample_output='4\n',
            cases=(
                TestCase('1\n7\n', '1\n'),
                TestCase('2\n1 1\n', '-1\n'),
                TestCase('5\n-1 -1 0 -1 -1\n', '3\n'),
                TestCase('7\n1 2 3 6 3 2 1\n', '4\n'),
                TestCase('4\n2 0 0 2\n', '2\n'),
                TestCase('6\n0 0 0 0 0 0\n', '1\n'),
                TestCase('5\n3 -1 -2 0 0\n', '4\n'),
                TestCase('7\n5 -2 4 0 4 -2 5\n', '4\n'),
                TestCase('3\n1000000000 0 1000000000\n', '2\n'),
                TestCase('5\n1 1 1 1 2\n', '-1\n'),
            ),
        ),
        ProblemSpec(
            title='Labeled Amount Query',
            difficulty='medium',
            time_limit=1500,
            memory_limit=128,
            source='simple parsing and counting',
            description=(
                'Each record gives a lowercase label and a signed amount. Add the amounts of '
                'all records whose label equals the final query label.'
            ),
            input_description=(
                'The first line contains n. The next n lines contain a label and an integer. '
                'The last line contains the queried label.'
            ),
            output_description='Print the sum of all amounts attached to the queried label.',
            sample_input='5\nred 4\nblue 9\nred -1\ngreen 8\nred 3\nred\n',
            sample_output='6\n',
            cases=(
                TestCase('1\napple 5\napple\n', '5\n'),
                TestCase('3\na 1\nb 2\na 4\na\n', '5\n'),
                TestCase('3\ncat -3\ndog 10\ncat 8\ncat\n', '5\n'),
                TestCase('5\nred 4\nblue 9\nred -1\ngreen 8\nred 3\nred\n', '6\n'),
                TestCase('3\nleft 7\nright 2\nleft -7\nmissing\n', '0\n'),
                TestCase(
                    '7\nred 1\nred 2\nblue 40\nred 3\nred 4\nred 5\ngreen -2\nred\n',
                    '15\n',
                ),
                TestCase('5\na -10\na 3\nb 4\na 7\nb -4\na\n', '0\n'),
                TestCase('4\nalpha 1000000000\nbeta -2\nalpha 1\nalpha -1\nbeta\n', '-2\n'),
                TestCase(
                    '9\npear 2\nplum 3\npear 5\nkiwi -1\npear 8\nplum 4\npear -4\nkiwi 6\npear 9\npear\n',
                    '20\n',
                ),
                TestCase(
                    '11\na 1\nb 2\na 3\nc 4\na 5\nb 6\na 7\nc 8\na 9\nb 10\na 11\nc\n',
                    '12\n',
                ),
            ),
        ),
    )
