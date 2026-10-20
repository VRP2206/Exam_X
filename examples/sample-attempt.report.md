# Grading report: FIT2014 Practice Exam (seed 42)

**Total: 26.5 / 120** (22%)

| Question | Marks | Method |
|---|---|---|
| 1 | 4 / 4 | exact |
| 2 | 2.5 / 4 | exact |
| 3 | 1.5 / 4 | blank, exact |
| 4 | 0 / 3 | blank |
| 5 | 0 / 7 | blank |
| 6 | 3 / 3 | exact |
| 7 | 0 / 6 | blank |
| 8 | 1 / 2 | exact |
| 9 | 0 / 6 | blank |
| 10 | 0 / 5 | blank |
| 11 | 0 / 5 | blank |
| 12 | 0 / 4 | blank |
| 13 | 4.5 / 6 | exact |
| 14 | 2 / 4 | llm-rubric |
| 15 | 3 / 4 | exact |
| 16 | 0 / 10 | blank |
| 17 | 5 / 7 | llm-rubric |
| 18 | 0 / 5 | blank |
| 19 | 0 / 4 | blank |
| 20 | 0 / 4 | blank |
| 21 | 0 / 2 | blank |
| 22 | 0 / 21 | blank |

## Question 1 — 4 / 4

**4 / 4** · _exact_

Correct.

## Question 2 — 2.5 / 4

**(a) 1.5 / 2** · _exact_

Missing: 'aaaba', 'aaaaba' Should not be listed: 'bab'

**(b) 1 / 2** · _exact_

Not equivalent to the required language: your answer rejects 'baba', which should be accepted. It agrees with the correct language on 100% of strings up to length 7.

## Question 3 — 1.5 / 4

**(a) 1.5 / 2** · _exact_

Missing: 'abbab', 'babbab'

**(b) 0 / 2** · _blank_

No answer given.

## Question 4 — 0 / 3

**0 / 3** · _blank_

No answer given.

## Question 5 — 0 / 7

**0 / 7** · _blank_

No answer given.

## Question 6 — 3 / 3

**3 / 3** · _exact_

Correct: your answer recognises exactly the required language.

## Question 7 — 0 / 6

**(a) 0 / 2** · _blank_

No answer given.

**(b) 0 / 2** · _blank_

No answer given.

**(c) 0 / 2** · _blank_

No answer given.

## Question 8 — 1 / 2

**1 / 2** · _exact_

Your grammar cannot generate 'bb' (and 15 more short strings in the language).

## Question 9 — 0 / 6

**0 / 6** · _blank_

No answer given.

## Question 10 — 0 / 5

**(a) 0 / 3** · _blank_

No answer given.

**(b) 0 / 2** · _blank_

No answer given.

## Question 11 — 0 / 5

**0 / 5** · _blank_

No answer given.

## Question 12 — 0 / 4

**0 / 4** · _blank_

No answer given.

## Question 13 — 4.5 / 6

**4.5 / 6** · _exact_

Wrong on 7 of 127 test inputs. For input ε (the empty string) the output should be '1' but your machine crashed off the left end with tape ''.

## Question 14 — 2 / 4

**(a) 2 / 2** · _llm-rubric_

Your answer correctly states the Church-Turing thesis. You have clearly conveyed the idea that any algorithmic computation can be performed by a Turing machine.

_Rubric:_ Correct statement of the Church-Turing thesis: 2 — The student's answer is correct and accurately reflects the Church-Turing thesis.

**(b) 0 / 2** · _llm-rubric_

Your answer is incorrect and does not address the Church-Turing thesis properly. The Church-Turing thesis is about the equivalence of different models of computation and the ability to simulate algorithms on Turing machines, not about the speed of Turing machines or compilation of programming languages.

_Rubric:_ Reason 1: Different approaches to defining computability end up being equivalent: 0 — This statement is incorrect. Turing machines are not fast; they are a theoretical model of computation, not a practical computing device. The speed of a Turing machine is not relevant to the Church-Turing thesis.; Reason 2: Long experience showing that algorithms can be implemented on Turing machines: 0 — This statement is vague and incorrect. The Church-Turing thesis is not about the speed or compilation of programming languages, but about the equivalence of different models of computation.

## Question 15 — 3 / 4

**(a) 1 / 1** · _exact_

Correct.

**(b) 1 / 1** · _exact_

Correct.

**(c) 0 / 1** · _exact_

Incorrect: the answer is Undecidable.

**(d) 1 / 1** · _exact_

Correct.

## Question 16 — 0 / 10

**(a) 0 / 1** · _blank_

No answer given.

**(b) 0 / 1** · _blank_

No answer given.

**(c) 0 / 1** · _blank_

No answer given.

**(d) 0 / 1** · _blank_

No answer given.

**(e) 0 / 1** · _blank_

No answer given.

**(f) 0 / 1** · _blank_

No answer given.

**(g) 0 / 1** · _blank_

No answer given.

**(h) 0 / 1** · _blank_

No answer given.

**(i) 0 / 1** · _blank_

No answer given.

**(j) 0 / 1** · _blank_

No answer given.

## Question 17 — 5 / 7

**5 / 7** · _llm-rubric_

You correctly applied the Pumping Lemma and chose a suitable string. However, you did not fully consider all possible cases for vxy, and your argument about pumping was too vague. To improve, explicitly consider all possible cases for vxy (e.g., vxy containing only a's, only b's, only c's, or combinations) and provide specific examples of how pumping leads to strings not in L.

_Rubric:_ State the Pumping Lemma for context-free languages: 2 — The student correctly references the Pumping Lemma and mentions the key conditions (|vxy| ≤ N and |vy| ≥ 1).; Choose a suitable string w = a^N b^N c^N and justify its length: 1 — The student correctly chooses w = a^N b^N c^N and implies that N is large, which is sufficient for the Pumping Lemma.; Apply the Pumping Lemma and consider all possible cases for vxy: 1 — The student does not explicitly consider all possible cases for vxy. They make a general claim that vxy cannot contain both a's and c's, but this is not justified and misses the detailed case analysis required.; Show that pumping leads to a string not in L in all cases: 1 — The student provides a general argument that pumping increases at most two of the three letters, but this is vague and lacks the specific examples and reasoning needed to show that the pumped string is not in L in all cases.

## Question 18 — 0 / 5

**(a) 0 / 1** · _blank_

No answer given.

**(b) 0 / 1** · _blank_

No answer given.

**(c) 0 / 1** · _blank_

No answer given.

**(d) 0 / 1** · _blank_

No answer given.

**(e) 0 / 1** · _blank_

No answer given.

## Question 19 — 0 / 4

**(a) 0 / 1** · _blank_

No answer given.

**(b) 0 / 1** · _blank_

No answer given.

**(c) 0 / 1** · _blank_

No answer given.

**(d) 0 / 1** · _blank_

No answer given.

## Question 20 — 0 / 4

**0 / 4** · _blank_

No answer given.

## Question 21 — 0 / 2

**0 / 2** · _blank_

No answer given.

## Question 22 — 0 / 21

**(a) 0 / 4** · _blank_

No answer given.

**(b) 0 / 6** · _blank_

No answer given.

**(c) 0 / 7** · _blank_

No answer given.

**(d) 0 / 2** · _blank_

No answer given.

**(e) 0 / 2** · _blank_

No answer given.
