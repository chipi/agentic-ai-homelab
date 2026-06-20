# Chip Huyen — production-AI writing

> **Source:** [huyenchip.com/blog/](https://huyenchip.com/blog/) —
> Chip Huyen's personal blog. Plus her books *AI Engineering* (2024),
> *Designing Machine Learning Systems* (2022), and her *Machine
> Learning Interviews* book.
> **Mission:** Brings AI into production; writes about AI system design
> rather than purely theoretical research.
>
> This page is a **homelab index of her LLM and ML-systems writing**.
> Her body of work bridges the gap between research papers and
> deployable systems — exactly the angle most reading lists miss.

## Why this page exists in our Reading section

Chip Huyen is **the practitioner-perspective complement** to Lilian
Weng's research-survey perspective. Where Lilian writes long-form
surveys of research literature, Chip writes hands-on "I built this,
here's what broke" essays from someone who has shipped production
LLM systems at scale (NVIDIA, Snorkel, her own ML platform startup
Claypot AI, and beyond).

The homelab's `llm-end-to-end.md` cites her as ☆ in § Blogs. This
page indexes the **specific posts** that back specific homelab
topics, particularly serving, evaluation, and the production
LLM-engineering stack.

## Reading order recommendation

For the homelab's stack specifically:

1. [**Building LLM applications for production**](https://huyenchip.com/2023/04/11/llm-engineering.html)
   (2023-04) — the canonical "what breaks when you actually ship LLMs"
   essay. **Read first.**
2. [**Building A Generative AI Platform**](https://huyenchip.com/2024/07/25/genai-platform.html)
   (2024-07) — system-architecture view of an end-to-end LLM platform
   (router, gateway, evaluation, monitoring).
3. [**RLHF: Reinforcement Learning from Human Feedback**](https://huyenchip.com/2023/05/02/rlhf.html)
   (2023-05) — explainer cited in the [a16z AI Canon](a16z-ai-canon.md)
   § Tech Deep Dive.
4. [**Generation configurations: temperature, top-k, top-p, and test
   time compute**](https://huyenchip.com/2024/01/16/sampling.html)
   (2024-01) — sampling-parameter reference; pairs with `llm-end-to-end`
   § 13 (Sampling).
5. [**Common pitfalls when building generative AI applications**](https://huyenchip.com/2025/01/16/ai-engineering.html)
   (2025-01) — hard-won failure-mode list.
6. [**Agents**](https://huyenchip.com/2025/01/07/agents.html)
   (2025-01) — practitioner take on agent architecture, complements
   Lilian Weng's research-side agent post.

The remaining posts are best consumed by topic.

## Generative AI & LLM engineering (most recent first)

| Date | Title | URL | Topic |
|---|---|---|---|
| 2025-01-16 | Common pitfalls when building generative AI applications | [link](https://huyenchip.com/2025/01/16/ai-engineering.html) | Failure modes |
| 2025-01-07 | Agents | [link](https://huyenchip.com/2025/01/07/agents.html) | Agent architecture |
| 2024-07-25 | Building A Generative AI Platform | [link](https://huyenchip.com/2024/07/25/genai-platform.html) | System design |
| 2024-01-16 | Generation configurations: temperature, top-k, top-p, and test time compute | [link](https://huyenchip.com/2024/01/16/sampling.html) | Sampling |
| 2023-04-11 | Building LLM applications for production | [link](https://huyenchip.com/2023/04/11/llm-engineering.html) | Production LLMs |
| 2023-05-02 | RLHF: Reinforcement Learning from Human Feedback | [link](https://huyenchip.com/2023/05/02/rlhf.html) | RLHF |
| 2023-06-07 | Generative AI Strategy | [link](https://huyenchip.com/2023/06/07/generative-ai-strategy.html) | Business |

## AI research & multimodality

| Date | Title | URL | Topic |
|---|---|---|---|
| 2024-03-14 | What I learned from looking at 900 most popular open source AI tools | [link](https://huyenchip.com/2024/03/14/ai-oss.html) | Tooling landscape |
| 2023-10-10 | Multimodality and Large Multimodal Models (LMMs) | [link](https://huyenchip.com/2023/10/10/multimodality.html) | LMMs survey |
| 2023-08-16 | Open challenges in LLM research | [link](https://huyenchip.com/2023/08/16/llm-research-open-challenges.html) | Field overview |

## ML infrastructure & MLOps

| Date | Title | URL | Topic |
|---|---|---|---|
| 2024-02-28 | Predictive Human Preference: From Model Ranking to Model Routing | [link](https://huyenchip.com/2024/02/28/predictive-human-preference.html) | Routing |
| 2023-01-08 | Self-serve feature platforms: architectures and APIs | [link](https://huyenchip.com/2023/01/08/self-serve-feature-platforms.html) | Feature platforms |
| 2020-12-30 | Machine Learning Tools Landscape v2 (+84 new tools) | [link](https://huyenchip.com/2020/12/30/mlops-v2.html) | Tooling survey |
| 2020-06-22 | What I learned from looking at 200 machine learning tools | [link](https://huyenchip.com/2020/06/22/mlops.html) | Tooling survey |

## ML systems & production

| Date | Title | URL |
|---|---|---|
| 2022-08-03 | Introduction to streaming for data scientists | [link](https://huyenchip.com/2022/08/03/streaming-for-data-scientists.html) |
| 2022-02-07 | Data Distribution Shifts and Monitoring | [link](https://huyenchip.com/2022/02/07/data-distribution-shifts-and-monitoring.html) |
| 2022-01-02 | Real-time machine learning: challenges and solutions | [link](https://huyenchip.com/2022/01/02/real-time-machine-learning-challenges-and-solutions.html) |
| 2021-09-13 | Why data scientists shouldn't need to know Kubernetes | [link](https://huyenchip.com/2021/09/13/data-science-infrastructure.html) |
| 2021-09-07 | A friendly introduction to machine learning compilers and optimizers | [link](https://huyenchip.com/2021/09/07/a-friendly-introduction-to-machine-learning-compilers-and-optimizers.html) |
| 2020-12-27 | Machine learning is going real-time | [link](https://huyenchip.com/2020/12/27/real-time-machine-learning.html) |

## Career & professional development

| Date | Title | URL |
|---|---|---|
| 2024-04-17 | Measuring personal growth | [link](https://huyenchip.com/2024/04/17/personal-growth.html) |
| 2022-12-27 | Books that made me think (as an engineer) | [link](https://huyenchip.com/2022/12/27/books-that-made-me-think.html) |
| 2021-02-27 | 7 reasons not to join a startup and 1 reason to | [link](https://huyenchip.com/2021/02/27/no-startup.html) |
| 2020-01-18 | Analysis of compensation, level, and experience details of 19k tech workers | [link](https://huyenchip.com/2020/01/18/tech-workers-compensation.html) |
| 2019-12-23 | Four lessons I learned after my first full-time job after college | [link](https://huyenchip.com/2019/12/23/post-college-graduation-job-lessons.html) |
| 2018-10-08 | Career advice for recent Computer Science graduates | [link](https://huyenchip.com/2018/10/08/career-advice-recent-cs-graduates.html) |

## Culture, research trends, education

| Date | Title | URL |
|---|---|---|
| 2019-12-28 | The books that shaped my decade | [link](https://huyenchip.com/2019/12/28/the-books-that-shaped-my-decade.html) |
| 2019-12-18 | Key trends from NeurIPS 2019 | [link](https://huyenchip.com/2019/12/18/key-trends-neurips-2019.html) |
| 2019-08-05 | Free online machine learning curriculum | [link](https://huyenchip.com/2019/08/05/free-online-machine-learning-curriculum.html) |
| 2019-05-12 | Top 8 trends from ICLR 2019 | [link](https://huyenchip.com/2019/05/12/top-8-trends-from-iclr-2019.html) |
| 2019-03-11 | A simple reason why there aren't more women in tech | [link](https://huyenchip.com/2019/03/11/why-there-arent-more-women-in-tech.html) |
| 2018-11-16 | How to build meaningful relationships after college | [link](https://huyenchip.com/2018/11/16/build-meaningful-relationships-after-college.html) |
| 2018-10-04 | SOTAWHAT — A script to keep track of state-of-the-art AI research | [link](https://huyenchip.com/2018/10/04/sotawhat.html) |
| 2018-03-30 | A survivor's guide to Artificial Intelligence courses at Stanford | [link](https://huyenchip.com/2018/03/30/guide-to-Artificial-Intelligence-Stanford.html) |
| 2017-07-28 | Confession of a so-called AI expert | [link](https://huyenchip.com/2017/07/28/confession-of-a-so-called-ai-expert.html) |

## Her books

| Book | Year | What it covers |
|---|---|---|
| **AI Engineering** | 2024 | The most recent — practical guide to building LLM applications: architecture, evaluation, prompt engineering, RAG, fine-tuning, inference optimization, agents. Released by O'Reilly. |
| **Designing Machine Learning Systems** | 2022 | The "production ML" book. Data engineering, feature stores, training, deployment, monitoring. Pre-LLM-era but foundational for the systems angle. |
| **Machine Learning Interviews** | 2019 | Interview prep — also functions as a curriculum / reading list. |

## Why her writing landed as canon

A few patterns worth understanding:

1. **System-architecture diagrams** — most posts include the boxes
   and arrows of "here's where this fits in the production pipeline."
   Bridges papers ↔ deployment in a way researchers rarely do.
2. **Survey + opinion** — she doesn't just enumerate options; she
   says which ones work and which break at scale. The opinions are
   load-bearing.
3. **Long-running themes** — the "I looked at N tools and here's
   what I learned" series spans 5+ years; the MLOps thread is
   chronological commentary on a maturing field.
4. **Books are extensions, not separate** — her O'Reilly books are
   organized versions of her blog series. If you read all her LLM
   posts, you've read most of *AI Engineering*.

## Cross-references

- [`llm-end-to-end.md`](llm-end-to-end.md) cites her as ☆ in §
  Blogs. Her sampling post backs § 13; her RLHF post is a non-citation
  background for § 18.
- [`a16z-ai-canon.md`](a16z-ai-canon.md) includes *Building LLM
  applications for production* and *RLHF: Reinforcement Learning from
  Human Feedback* in their Practical Guides and Tech Deep Dive
  sections respectively.
- [`README.md`](README.md) — author-archive index pages don't apply
  ★/☆/·.
