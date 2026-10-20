# Grading report: FIT2014 Practice Exam (seed 42)

**Total: 23.5 / 120** (20%)

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
| 17 | 2 / 7 | llm-rubric |
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

Your answer is correct and captures the essence of the Church-Turing thesis. The model solution states it as 'Any function which can defined by an algorithm can be represented by a Turing Machine,' while your version says 'Anything that can be computed by an algorithm can be computed by a Turing machine.' Both are valid formulations. Well done!

_Rubric:_ Correct answer (compare with the official solution): 2 — The student's answer is essentially equivalent to the model solution, with slightly different wording. Both convey the core idea of the Church-Turing thesis.

**(b) 0 / 2** · _llm-rubric_

Your answer is incorrect. The Church-Turing thesis is not about the speed of Turing machines or programming languages compiling to them. It is about the equivalence of different computational models and the idea that any algorithm can be simulated by a Turing machine. Two correct reasons are: (1) different approaches to defining computability end up being equivalent, and (2) long experience shows that algorithms can be implemented as programs and thus on Turing machines.

_Rubric:_ Correct answer (compare with the official solution): 0 — The student's answer is incorrect. The Church-Turing thesis is not about the speed of Turing machines or the compilation of programming languages to Turing machines. It is about the equivalence of different models of computation and the limits of computability.

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

## Question 17 — 2 / 7

**2 / 7** · _llm-rubric_

Your answer is concise but lacks the detailed case analysis required to apply the Pumping Lemma correctly. You need to clearly state the Pumping Lemma, justify the choice of string, and consider all possible cases for vxy. Make sure to show that pumping leads to a string not in L in each case.

_Rubric:_ State the Pumping Lemma for context-free languages: 1 — The student mentions the Pumping Lemma but does not clearly state it. A full statement would include the form w = uvxyz, the conditions on |vxy| and |vy|, and the requirement that uv^i xy^i z ∈ L for all i ≥ 0.; Choose a suitable string w = a^N b^N c^N and justify its length: 1 — The student chooses w = a^N b^N c^N but does not clearly justify its length (e.g., that it is longer than the pumping length).; Apply the Pumping Lemma and consider all possible cases for vxy: 0 — The student does not consider all possible cases for vxy. They incorrectly assume that vxy cannot contain both a's and c's, which is not necessarily true. This is a critical omission.; Show that pumping leads to a string not in L in all cases: 0 — The student does not provide a detailed argument showing that pumping leads to a string not in L. The reasoning is too vague and lacks the necessary case analysis.

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
