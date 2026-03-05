# Source Playbook for China Politics

Use source tiers to control reliability and narrative bias.

## Tier T0: Highest Political Weight
- Core communiques from top-level Party meetings.
- Top-leadership authoritative speeches and direct strategic directives.

Use for:
- Final top-line political signal and strategic intent.

## Tier T1: Central Normative and Authorized Core Distribution
- `gov.cn` central policy texts and central normative documents.
- `xinhuanet.com` authorized releases and central text republication.
- `npc.gov.cn` national legal process and enacted legal texts.

Use for:
- Formal policy basis, legal force, and authoritative wording.

## Tier T2: Ministerial/Institutional Implementation and Central Commentary
- Ministry regulations, ministry notices, and implementation circulars.
- `people.com.cn`, `cctv.com` and comparable central media commentary.

Use for:
- Implementation architecture, policy interpretation, and execution priorities.

## Tier T3: Local and Peripheral Interpretation
- Local government implementation files and region-level notices.
- Local official media and peripheral explanatory articles.

Use for:
- Local execution variation, practical constraints, and pace of rollout.

## Tier Resolution Rule
1. Treat T0/T1 as baseline political direction.
2. Use T2 to explain operationalization, not to overturn T0/T1.
3. Use T3 to map execution heterogeneity and local frictions.
4. When T3 conflicts with T0/T1, report as implementation deviation instead of doctrinal reversal.

## Horizontal Search Strategy
1. Start from Tier T0/T1 for baseline facts.
2. Add Tier T2 to capture official narrative signals and execution logic.
3. Add Tier T3 and external reporting to surface divergence, omissions, and second-order effects.
4. Record conflicts, then test conflicts against Tier T0/T1 wording and dates.

## Vertical Search Strategy
1. Locate predecessor policy text (usually 1-5 years earlier).
2. Locate implementation notices and pilot documents.
3. Locate follow-up evaluations, inspections, or rectification notices.
4. Build timeline with explicit dates and policy verbs.

## Query Design Pattern
- Core topic query: `"<topic>" + 通知/意见/方案/规定`
- Institutional query: `"<topic>" + <agency> + 发布/印发`
- Lineage query: `"<topic>" + 历史 + 沿革 + 政策`
- Implementation query: `"<topic>" + 落地 + 试点 + 通报`
- Divergence query: `"<topic>" + 争议 + 执行 + 地方`

## Citation Rule
- Include source URL, title, publication date, and retrieval date.
- Quote short, decisive fragments only when needed.
- If no primary source is found, state this explicitly and lower confidence.
- Add tier label (`T0/T1/T2/T3`) per citation and explain tier assignment when ambiguous.
