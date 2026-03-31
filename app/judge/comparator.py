class Comparator:
    def compare(self, user_output: str, expected_output: str) -> bool:
        def normalize(text):
            text = text.strip().replace('\r\n', '\n').replace('\r', '\n')
            lines = [line.rstrip() for line in text.split('\n')]
            # Remove trailing empty lines
            while lines and lines[-1] == '':
                lines.pop()
            return lines

        return normalize(user_output) == normalize(expected_output)

    def compare_float(self, user_output: str, expected_output: str, precision: int = 6) -> bool:
        import re
        user_tokens = re.split(r'\s+', user_output.strip())
        expected_tokens = re.split(r'\s+', expected_output.strip())
        if len(user_tokens) != len(expected_tokens):
            return False
        for u, e in zip(user_tokens, expected_tokens):
            try:
                fu = float(u)
                fe = float(e)
                if abs(fu - fe) >= 10 ** (-precision):
                    return False
            except ValueError:
                if u != e:
                    return False
        return True
