# Phoenix experiment results

Dataset `nsf-eval-1` (10 multi-step questions). Agent claude-sonnet-5-5, judge claude-opus-5-5. One run per prompt version; the agent is not deterministic.

| Prompt | Correct (match_expected_response) | In scope (check_answer_scope) |
|---|---|---|
| v1 | 10/10 | 10/10 |
| v2 | 10/10 | 10/10 |

| Question | Gold answer | v1: label | v2: label |
|---|---|---|---|
| What is the title of the NSF award mentioning "CRISPR" with a 2018 start date that has the larg | RII Track-2 FEC: Systems Genetics Studies on Rice  | correct | correct |
| Did the NSF "Robust Intelligence" program start more awards in 2019 or in 2020, and by how many | 2019, by 25 awards (170 versus 145) | correct | correct |
| Who is the principal investigator on the NSF award starting in 2020 at Carnegie Mellon Universi | Paola Buitrago | correct | correct |
| Of Stanford University, Carnegie Mellon University and Massachusetts Institute of Technology, w | Massachusetts Institute of Technology | correct | correct |
| Between 2018 and 2022 inclusive, in which start year did NSF begin the most awards mentioning " | 2021 | correct | correct |
| Of the NSF awards mentioning "CRISPR" that started in 2019, which funding program (as NSF names | Plant Genome Research Project | correct | correct |
| Among the NSF awards mentioning "CRISPR" that started in 2019, which institution holds the most | University of Wisconsin-Madison | correct | correct |
| How many more NSF awards mentioning "quantum" started in 2021 than in 2019? | 101 | correct | correct |
| Counting NSF awards whose start date falls in 2019, 2020 or 2021 and whose records mention "qua | 2190 | correct | correct |
| Add up the funds obligated to date for NSF awards 1753742, 1753559 and 2138259. What is the com | 13755019 | correct | correct |
