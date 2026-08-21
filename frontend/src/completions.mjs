const common = [
    { label: 'if', type: 'keyword', detail: 'condition', apply: 'if' },
    { label: 'else', type: 'keyword', detail: 'branch', apply: 'else' },
    { label: 'for', type: 'keyword', detail: 'loop', apply: 'for' },
    { label: 'while', type: 'keyword', detail: 'loop', apply: 'while' },
    { label: 'break', type: 'keyword', detail: 'loop control', apply: 'break' },
    { label: 'continue', type: 'keyword', detail: 'loop control', apply: 'continue' },
    { label: 'return', type: 'keyword', detail: 'function result', apply: 'return' },
];

const cpp = [
    ...common,
    { label: '#include <bits/stdc++.h>', type: 'keyword', detail: 'header', apply: '#include <bits/stdc++.h>' },
    { label: 'int main()', type: 'snippet', detail: 'entry point', apply: 'int main() {\n    ${1}\n}${0}' },
    { label: 'vector', type: 'class', detail: 'std::vector', apply: 'vector' },
    { label: 'string', type: 'class', detail: 'std::string', apply: 'string' },
    { label: 'map', type: 'class', detail: 'std::map', apply: 'map' },
    { label: 'set', type: 'class', detail: 'std::set', apply: 'set' },
    { label: 'priority_queue', type: 'class', detail: 'std::priority_queue', apply: 'priority_queue' },
    { label: 'sort', type: 'function', detail: 'algorithm', apply: 'sort' },
    { label: 'lower_bound', type: 'function', detail: 'algorithm', apply: 'lower_bound' },
    { label: 'upper_bound', type: 'function', detail: 'algorithm', apply: 'upper_bound' },
    { label: 'priority_queue<int>', type: 'snippet', detail: 'max heap', apply: 'priority_queue<int> ${1};${0}' },
    { label: 'for (int i = 0; i < n; ++i)', type: 'snippet', detail: 'indexed loop', apply: 'for (int i = 0; i < n; ++i) {\n    ${1}\n}${0}' },
    { label: 'long long', type: 'type', detail: '64-bit integer', apply: 'long long' },
    { label: 'cin', type: 'function', detail: 'standard input', apply: 'cin' },
    { label: 'cout', type: 'function', detail: 'standard output', apply: 'cout' },
];

const java = [
    ...common,
    { label: 'public static void main(String[] args)', type: 'snippet', detail: 'entry point', apply: 'public static void main(String[] args) {\n    ${1}\n}${0}' },
    { label: 'Scanner', type: 'class', detail: 'java.util.Scanner', apply: 'Scanner' },
    { label: 'ArrayList', type: 'class', detail: 'java.util.ArrayList', apply: 'ArrayList' },
    { label: 'HashMap', type: 'class', detail: 'java.util.HashMap', apply: 'HashMap' },
    { label: 'HashSet', type: 'class', detail: 'java.util.HashSet', apply: 'HashSet' },
    { label: 'Arrays.sort', type: 'function', detail: 'java.util.Arrays', apply: 'Arrays.sort' },
    { label: 'Collections.sort', type: 'function', detail: 'java.util.Collections', apply: 'Collections.sort' },
    { label: 'StringBuilder', type: 'class', detail: 'java.lang.StringBuilder', apply: 'StringBuilder' },
    { label: 'System.out.println', type: 'function', detail: 'standard output', apply: 'System.out.println' },
    { label: 'for (int i = 0; i < n; i++)', type: 'snippet', detail: 'indexed loop', apply: 'for (int i = 0; i < n; i++) {\n    ${1}\n}${0}' },
    { label: 'import java.util.*;', type: 'keyword', detail: 'common imports', apply: 'import java.util.*;' },
    { label: 'int', type: 'type', detail: '32-bit integer', apply: 'int' },
    { label: 'long', type: 'type', detail: '64-bit integer', apply: 'long' },
];

const python = [
    ...common,
    { label: 'def', type: 'keyword', detail: 'function definition', apply: 'def' },
    { label: 'class', type: 'keyword', detail: 'class definition', apply: 'class' },
    { label: 'import', type: 'keyword', detail: 'module import', apply: 'import' },
    { label: 'from', type: 'keyword', detail: 'module import', apply: 'from' },
    { label: 'print', type: 'function', detail: 'standard output', apply: 'print' },
    { label: 'len', type: 'function', detail: 'sequence length', apply: 'len' },
    { label: 'range', type: 'function', detail: 'integer sequence', apply: 'range' },
    { label: 'enumerate', type: 'function', detail: 'indexed iteration', apply: 'enumerate' },
    { label: 'list', type: 'class', detail: 'built-in sequence', apply: 'list' },
    { label: 'dict', type: 'class', detail: 'built-in mapping', apply: 'dict' },
    { label: 'set', type: 'class', detail: 'built-in collection', apply: 'set' },
    { label: 'input', type: 'function', detail: 'standard input', apply: 'input' },
    { label: 'for i in range(n):', type: 'snippet', detail: 'indexed loop', apply: 'for i in range(n):\n    ${1}${0}' },
    { label: 'def solve():', type: 'snippet', detail: 'solution function', apply: 'def solve():\n    ${1}${0}' },
    { label: 'if __name__ == "__main__":', type: 'snippet', detail: 'program entry', apply: 'if __name__ == "__main__":\n    ${1}${0}' },
    { label: 'int', type: 'function', detail: 'integer conversion', apply: 'int' },
    { label: 'str', type: 'class', detail: 'string conversion', apply: 'str' },
];

export const LANGUAGE_COMPLETIONS = Object.freeze({ cpp, java, python });

export function getCompletionOptions(language) {
    return LANGUAGE_COMPLETIONS[language] ? [...LANGUAGE_COMPLETIONS[language]] : [];
}

export function filterCompletionOptions(language, prefix, limit = 40) {
    const normalizedPrefix = typeof prefix === 'string' ? prefix : '';
    const safeLimit = Number.isInteger(limit) && limit > 0 ? limit : 40;
    return getCompletionOptions(language)
        .filter((option) => option.label.startsWith(normalizedPrefix))
        .slice(0, safeLimit);
}
