class Comparator:
    """Exact comparison after whitespace normalisation.

    There is no tolerance-based float mode: verdicts must be reproducible, and a
    per-problem tolerance would have to be part of the problem definition first.
    """

    def compare(self, user_output: str, expected_output: str) -> bool:
        def normalize(text):
            text = text.strip().replace('\r\n', '\n').replace('\r', '\n')
            lines = [line.rstrip() for line in text.split('\n')]
            # Remove trailing empty lines
            while lines and lines[-1] == '':
                lines.pop()
            return lines

        return normalize(user_output) == normalize(expected_output)
