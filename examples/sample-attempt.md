# Sample attempt at examples/practice-42.json

A deliberately mixed attempt (some answers right, some wrong, some missing) used to
demonstrate `examx grade examples/practice-42.json examples/sample-attempt.md`.

## Q1
(B ∨ G ∨ C ∨ L)

## Q2
### (a)
ε, a, aa, ba, aaa, aba, aaaa, aaba, baba, aaaaa, aaaaaa, bab

### (b)
```
start: 1
final: 1 2 4
1 a 2
2 a 2
1 b 3
3 a 4
2 b 3
4 b 5
5 a 6
```

## Q3
### (a)
ε, ab, bab, abab, babab, ababab

## Q6
```
(a∪b)*aba(a∪b)*
```

## Q8
```
S → aSb | b
```

## Q13
```
start: 1
halt: H
1 0 -> 1 0 R
1 1 -> 1 1 R
1 Δ -> 2 Δ L
2 1 -> 2 0 L
2 0 -> H 1 R
```

## Q14
### (a)
Anything that can be computed by an algorithm can be computed by a Turing machine.

### (b)
Turing machines are very fast, and every programming language compiles to Turing machines.

## Q15
(a) Decidable
(b) Decidable
(c) Decidable
(d) Undecidable

## Q17
Suppose L = {a^n b^n c^n} is context-free and let w = a^N b^N c^N where N is large.
By the pumping lemma w = uvxyz with |vxy| ≤ N, and vy not empty. Since |vxy| ≤ N, vxy cannot contain
both a's and c's. So pumping up (i = 2) increases the number of at most two of the three letters,
leaving at least one letter count unchanged, so uv²xy²z is not in L. Contradiction, so L is not context-free.
