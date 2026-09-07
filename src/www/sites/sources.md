# LLM self-hosting source snapshot · 2026-09-07

`data.py` contains the immutable numeric snapshot used by the calculator. These are USD planning prices, checked against public sources on September 7, 2026; they are not a capacity quote. Review API rates by October 7, 2026 and cloud rates before a commitment.

## Compute

[Google's accelerator pricing table](https://cloud.google.com/products/compute/pricing/accelerator-optimized?hl=en) lists whole machines, including attached GPUs, vCPUs, host RAM, and bundled Local SSD where applicable. Use the **Compute Resource CUD** columns, not the flexible-CUD columns. G2/G4 use Iowa (`us-central1`); the A-series values come from the published reference table. Availability and regional pricing need a separate quote.

| Machine        | GPU memory | On-demand/hour | 1-year resource CUD/hour | 3-year resource CUD/hour |
| -------------- | ---------- | -------------- | ------------------------ | ------------------------ |
| g2-standard-12 | 1 × 24 GB  | 1.000416348    | 0.630262303              | 0.450187356              |
| g4-standard-48 | 1 × 96 GB  | 4.49993        | 3.105                    | 1.97945                  |
| a2-ultragpu-1g | 1 × 80 GB  | 5.06879789     | 4.199690411              | 3.499997559              |
| a3-highgpu-8g  | 8 × 80 GB  | 88.490000119   | 61.383674231             | 38.864383195             |
| a3-ultragpu-8g | 8 × 141 GB | 84.806908493   | 58.471933151             | 37.208420822             |
| a4-highgpu-8g  | 8 × 180 GB | Unavailable    | 88.9272                  | 56.7072                  |

A4 Flex-start is $64.44/hour. Its provisioning queue and bounded run duration do not establish continuous serving availability. The calculator does not stack discounts. Commitments pay for the full term even when nodes are idle and require GPU reservations: [GPU commitment requirements](https://cloud.google.com/products/compute/gpus-pricing), [committed-use billing](https://docs.cloud.google.com/compute/docs/instances/signing-up-committed-use-discounts).

The [GKE cluster fee](https://cloud.google.com/kubernetes-engine/pricing) remains $0.10/hour; no free-tier credit is assumed. Additional disks, network transfers, load balancers, licenses, and operations belong in the additional hosting budget.

[Machine specifications](https://docs.cloud.google.com/compute/docs/accelerator-optimized-machines), [GKE Standard GPU support](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/gpus), and [GKE inference guidance](https://docs.cloud.google.com/kubernetes-engine/docs/best-practices/machine-learning/inference) support the L4/G2 and RTX PRO 6000 Blackwell Server Edition/G4 entries. G2 uses a 48 GiB host configuration to leave more model-loading room than the smallest 16 GiB VM. Driver support, checkpoint format, host RAM, and KV cache still require a pilot.

## API baselines

| Provider model   | Standard input/M | Output/M | Cache read/M | Cache write/M | Combined context | Max output |
| ---------------- | ---------------- | -------- | ------------ | ------------- | ---------------- | ---------- |
| Gemini 3.8 Flash | 0.75             | 3.75     | 0.075        | Storage fees  | 1,048,576        | 65,536     |
| Claude Sonnet 5  | 2                | 10       | 0.20         | 2.50          | 1,000,000        | 128,000    |
| GPT-6 Astra      | 10               | 50       | 1            | 12.50         | 1,050,000        | 128,000    |

- [Astra model pricing and limits](https://developers.openai.com/api/docs/models/gpt-6-astra): input over 272,000 tokens doubles input/cache rates and multiplies output by 1.5 for the entire request. These are standard API token prices, separate from ChatGPT/Codex subscriptions and tool charges.
- [Gemini pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.8-flash): introductory rates end December 31, 2026. Input, output, cache reads, and $0.50/M token-hour storage double on January 1, 2027. The [model card](https://ai.google.dev/gemini-api/docs/models/gemini-3.8-flash) lists the input and output limits; the [token guide](https://ai.google.dev/gemini-api/docs/tokens#context-window) defines the context window as their combined budget.
- [Claude pricing](https://platform.claude.com/docs/en/about-claude/pricing): Sonnet 5's $2/$10 rates are now standard; the announced September increase was canceled. The [Sonnet 5 model guide](https://platform.claude.com/docs/en/models/sonnet-5/whats-new-sonnet-5) documents its context and output limits.

Batch rates remain half the standard input/output rates. Cache rules and provider links remain attached to each `APIBaseline`; batch and caching are modeled separately.

## Models and hardware guidance

The [Artificial Analysis leaderboard](https://artificialanalysis.ai/models) and the linked per-model pages were checked for the existing ten-model snapshot. Qwen3.8 27B's index is now 41.4059 and Inkling's is 32.1665; the ordering is unchanged. Memory calculations continue to use total parameters, including inactive MoE weights.

Hardware starting points are static per-model references, not vendor benchmarks or results of the current scenario. They use 4-bit weights plus a fixed 25% memory reserve and select the fewest hosts, then the smallest aggregate VRAM, from the hardware list. Multi-host references use A3/A4 only. This is a minimum memory baseline; precision, context, runtime support, model quality, and speed still need validation. Selecting a model displays its reference; the hint has no action link and does not alter inputs.
