# Innovation Radar — MVP Interface Plan

## Overview

The goal of the Innovation Radar interface is to provide Orange Business users with a simple and actionable way to:

> **Discover → Understand → Validate → Act**

The interface should transform the output of the research and AI pipeline into a clear list of **Opportunity Spaces** defined as:

`Vertical × Use Case × Technology`

The interface is designed for three main user groups:

* **Strategists & Innovators** — identify emerging opportunities, market trends, and areas where Orange Business should invest or position itself.
* **Sales Teams** — identify opportunities relevant to customers, accounts, and target verticals.
* **Presales & Proposal Teams** — understand use cases, technologies, Orange capabilities, references, partners, and evidence that can support a customer proposal.

The interface should **not** be a generic news dashboard. Its purpose is to help users understand **what matters, why it matters, and what they should do next**.

---

## 1. MVP Objectives

The MVP interface should allow a user to answer six questions:

1. **What is the opportunity?**
2. **Why is it important now?**
3. **How attractive is it?**
4. **Can Orange Business win it?**
5. **What evidence supports the ranking?**
6. **What should I do next?**

### Core user journey

```text
Discover
   ↓
Understand
   ↓
Validate
   ↓
Act
```

---

# 2. MVP Scope

The first version should focus on a small number of features that demonstrate the core value of the Innovation Radar.

### Must Have

* [ ] Opportunity dashboard / list
* [ ] Opportunity cards
* [ ] Opportunity detail page
* [ ] Attractiveness score
* [ ] Right-to-Win score
* [ ] Urgency
* [ ] Confidence level
* [ ] Score breakdown
* [ ] "Why Hot Now?" section
* [ ] Evidence / sources
* [ ] Orange Business relevance / capabilities
* [ ] Recommended next action
* [ ] Basic filtering
* [ ] Refresh Data button
* [ ] Loading / error / empty states
* [ ] Basic support for the three target user profiles
* [ ] Mock data support for development before backend integration

### Nice to Have

* [ ] Persona-specific dashboards
* [ ] Customer/account overlap
* [ ] Orange capability mapping
* [ ] Opportunity evolution over time
* [ ] Compare opportunities
* [ ] Advanced filtering

### Post-MVP

* [ ] Conversational "Ask the Radar" assistant
* [ ] Custom websites
* [ ] Custom keywords / topics
* [ ] Personalised research
* [ ] Advanced opportunity clustering
* [ ] Alerts
* [ ] User accounts
* [ ] Saved opportunities
* [ ] PowerPoint/PDF export
* [ ] Collaboration/comments

---

# 3. Target Users

## 3.1 Strategists & Innovators

### Main question

> **Where should Orange Business invest or position itself?**

### Information to prioritise

* Market attractiveness
* Market momentum
* Urgency
* Emerging trends
* Technology maturity
* Strategic relevance
* Long-term opportunity
* Confidence

### Example actions

* Assess as a growth opportunity
* Monitor the market
* Identify capability gaps
* Assess potential partners
* Add to strategic roadmap

---

## 3.2 Sales Teams

### Main question

> **Which customers could I approach, and why?**

### Information to prioritise

* Customer relevance
* Existing account overlap
* Buying signals
* Target vertical
* Urgency
* Relevant Orange references
* Recommended sales action

### Example actions

* Target an existing account
* Open a customer conversation
* Organise a customer workshop
* Use an existing reference case
* Contact the account team

---

## 3.3 Presales & Proposal Teams

### Main question

> **Can Orange Business actually deliver a credible solution?**

### Information to prioritise

* Use case
* Technology
* Orange offerings
* Technical maturity
* Reference cases
* Partners
* Existing capabilities
* Proof points

### Example actions

* Identify relevant Orange offerings
* Build a technical deep-dive
* Assess partner capabilities
* Reuse an existing architecture/reference
* Identify technical gaps

---

# 4. Application Structure

The MVP should initially contain three main areas:

```text
Innovation Radar
│
├── Dashboard
│   ├── Opportunity list
│   ├── Filters
│   └── Refresh Data
│
├── Opportunity Detail
│   ├── Overview
│   ├── Why Hot Now?
│   ├── Market Attractiveness
│   ├── Orange Right to Win
│   ├── Evidence
│   └── Recommended Action
│
└── User Perspective
    ├── Strategist
    ├── Sales
    └── Presales
```

---

# 5. Dashboard

The dashboard is the main entry point of the application.

It should allow users to quickly identify the most relevant Opportunity Spaces.

### Example

```text
Innovation Radar

[ Strategist ] [ Sales ] [ Presales ]

[ Refresh Data ]

Filters:
[ Vertical ] [ Technology ] [ Urgency ] [ Confidence ] [ Min Score ]

------------------------------------------------------------
Opportunity                              Score   Urgency
------------------------------------------------------------
Banking × WAN Security × Analytics        8.8     NOW
Government × Sovereign AI                 8.6     NOW
Insurance × Agentic AI                    8.2     NEXT
Mining × Private 5G                       7.5     NEXT
------------------------------------------------------------
```

### Ranking

The default ranking should ideally consider:

* Attractiveness
* Urgency
* Confidence

A highly attractive opportunity that is several years away should not necessarily appear above a slightly less attractive opportunity that requires action now.

---

# 6. Opportunity Card

Each Opportunity Space should be represented by a compact card.

### Example

```text
┌──────────────────────────────────────────────┐
│ Banking × WAN Security × Network Analytics  │
│                                              │
│ 8.8 / 10       NOW       HIGH CONFIDENCE    │
│                                              │
│ Why hot now                                  │
│ ↑ New customer deployments                  │
│ ↑ Regulatory pressure                       │
│ ↑ Cybersecurity investment                  │
│                                              │
│ Orange Fit: 9.2 / 10                        │
│                                              │
│ View opportunity →                           │
└──────────────────────────────────────────────┘
```

The card should provide enough information to understand the opportunity without opening it.

Detailed evidence and scoring explanations should remain on the Opportunity Detail page.

---

# 7. Opportunity Detail

The Opportunity Detail page is the **core page of the MVP**.

It should make the ranking explainable.

### Example

```text
# Banking × WAN Security × Network Analytics

8.8 / 10
NOW
HIGH CONFIDENCE

## Why Hot Now

Short, evidence-based explanation of why this opportunity
is becoming important now.

## Why It Matters

Explain the customer value and why the topic is relevant
to Orange Business.

## Market Attractiveness

Market Demand       9.1 / 10
Evidence Quality    8.4 / 10
Source Diversity    8.1 / 10
Momentum            9.0 / 10
Orange Relevance    9.2 / 10

Overall             8.8 / 10

## Orange Business Right to Win

Offering Fit        9.2 / 10
Customer Overlap    8.5 / 10
Reference Cases     7.5 / 10
Partner Readiness   8.0 / 10

Right to Win        8.3 / 10

## Evidence

[Regulation]
Source: ...
Date: ...

[Market Trend]
Source: ...
Date: ...

[Buying Signal]
Source: ...
Date: ...

## Orange Business

- Relevant offering
- Existing customer overlap
- Relevant partner
- Existing reference
- Relevant capability

## Recommended Next Action

Organise a customer workshop with relevant banking accounts.
```

---

# 8. Explainable Scoring

A key principle of the Innovation Radar is:

> **If a user cannot explain why an opportunity is ranked, the score is not good enough.**

Therefore, the interface should not only display a final score.

Users should be able to understand the factors behind the score.

### Example

```text
Why 8.8?

Market Demand       █████████░  9.1
Evidence Quality    ████████░░  8.4
Source Diversity    ████████░░  8.1
Momentum            █████████░  9.0
Orange Relevance    █████████░  9.2
```

The same principle applies to the **Right-to-Win** score.

---

# 9. Evidence

Every ranked Opportunity Space should have traceable evidence.

Each evidence item should contain, when available:

* Signal type
* Date
* Claim
* Source
* Source reliability
* Link to the original source

### Signal types

* Regulation
* Buying Signal
* Market Trend
* Market Move
* Technology Maturity
* Proof Signal

### Example

```text
[REGULATION]

EU regulation introduces new requirements for...

Date: 2026-05-12
Source reliability: 10/10
Source: EUR-Lex
```

The evidence section is important because the radar should be **evidence-driven rather than simply AI-generated**.

---

# 10. User Perspectives

The same Opportunity Space should be useful to all three personas, but the information emphasised can differ.

## Strategist View

Prioritise:

```text
Market attractiveness
Market momentum
Urgency
Technology maturity
Strategic relevance
Emerging opportunities
```

Possible actions:

```text
→ Assess as a growth opportunity
→ Monitor market
→ Identify capability gaps
→ Assess potential partners
→ Add to strategic roadmap
```

---

## Sales View

Prioritise:

```text
Customer relevance
Account overlap
Buying signals
Target vertical
Urgency
Orange references
```

Possible actions:

```text
→ Target an existing account
→ Open a customer conversation
→ Organise a workshop
→ Use a reference case
→ Contact the account team
```

---

## Presales View

Prioritise:

```text
Use case
Technology
Orange offering
Technical maturity
Reference cases
Partners
Capabilities
```

Possible actions:

```text
→ Identify relevant Orange offerings
→ Build a technical deep-dive
→ Assess partner capabilities
→ Reuse an existing architecture/reference
→ Identify technical gaps
```

---

# 11. "Why This Matters to Me?"

A useful UI concept is to dynamically explain the relevance of an opportunity depending on the selected user perspective.

### Example

```text
WHY THIS MATTERS

For Strategy
High-growth market aligned with Orange's
trusted cybersecurity strategy.

For Sales
12 existing Orange banking customers may
be relevant to this opportunity.

For Presales
Existing security analytics capabilities,
2 reference cases and relevant partners.
```

This allows the same underlying opportunity to serve all three user groups without building three separate applications.

---

# 12. Filters

The MVP should provide basic filters.

### Generic filters

* Vertical
* Technology
* Urgency
* Confidence
* Minimum score

### Example

```text
Vertical:     [Banking]
Technology:   [All]
Urgency:      [NOW]
Confidence:   [HIGH]
Min Score:    [7.5]
```

### Future persona-specific filters

#### Sales

* Customer
* Geography
* Buying signal
* Customer overlap

#### Presales

* Technology
* Use case
* Orange offering
* Reference case
* Partner

#### Strategy

* Market maturity
* Market momentum
* Strategic relevance
* Urgency

---

# 13. Refresh Data

The dashboard should include a clear **Refresh Data** button.

The button will eventually trigger the backend data pipeline.

### Example UI

```text
[ Refresh Data ]

Refreshing Innovation Radar...

✓ Collecting new sources
✓ Processing new articles
✓ Extracting signals
✓ Updating opportunities
✓ Recalculating scores

Last update:
18 August 2026 — 10:42
```

The interface should support:

* Loading state
* Successful refresh
* Failed refresh
* Last successful update
* No new data state

The actual data pipeline will be implemented separately.

---

# 14. Data Contract

UI development should not depend on the AI pipeline being finished.

The frontend should initially work with mock data based on a common data structure.

### Example

```json
{
  "title": "Banking × WAN Security × Network Analytics",
  "attractiveness": 8.8,
  "right_to_win": 8.3,
  "urgency": "NOW",
  "confidence": "HIGH",
  "why_hot_now": "...",
  "why_it_matters": "...",
  "evidence": [],
  "orange_capabilities": [],
  "recommended_action": "..."
}
```

This does not have to be the final backend schema.

Its purpose is to establish a basic contract between the UI and backend teams.

### Important

**UI development should start with mock data.**

The frontend should not wait for the agents, Tavily pipeline, scoring system, or database to be completed.

---

# 15. UI States

The application should include basic states from the beginning.

## Loading

```text
Loading opportunities...
```

## Empty

```text
No opportunities match your current filters.
```

## Error

```text
Unable to refresh data.

Last successful update:
18 August 2026
```

## No New Data

```text
Your radar is already up to date.
```

These states should be implemented before the final integration.

---

# 16. Future Features

The following features should be considered **Phase 2+** and should not block the MVP.

## 16.1 Personalised Research

Users could eventually define:

* Custom websites
* Custom keywords
* Custom topics

Example:

```text
Custom Research

+ Add website
+ Add keyword

Maximum: 10 custom items
```

This could become a potential selling point of the product.

---

## 16.2 Ask the Radar

A future conversational interface could allow users to interact with the existing opportunity dataset.

Example:

```text
Ask the Radar

"Show me only opportunities related to public transport."

[ Ask ]
```

The AI could then filter or re-rank existing opportunities based on the user's request.

---

## 16.3 Opportunity Clustering

Similar signals should eventually be merged into a single Opportunity Space.

Example:

```text
Bank network monitoring
Bank WAN security
Bank network analytics
Bank cyber visibility
```

Could become:

```text
Banking × WAN Security × Network Analytics
```

This will help prevent duplicate or overly similar opportunities from appearing in the radar.

---

## 16.4 Opportunity Evolution

The UI could eventually display how an opportunity changes over time.

```text
Attractiveness

June    6.8
July    7.5
August  8.8
```

And explain the changes:

```text
Why did the score increase?

↑ New regulation
↑ Customer deployments
↑ Market investment
↑ Orange strategic relevance
```

This would support the idea of a **living Innovation Radar**.

---

## 16.5 Compare Opportunities

Users could compare two or three Opportunity Spaces.

```text
                         Banking       Government

Attractiveness             8.8            8.6
Right to Win               8.3            9.2
Urgency                    NOW            NOW
Confidence                 HIGH           HIGH
Market Momentum            9.1            8.7
Orange Relevance            9.2            9.6
```

---

# 17. Development Priorities

## 🟢 Must Have

* [ ] Dashboard
* [ ] Opportunity cards
* [ ] Opportunity detail
* [ ] Attractiveness score
* [ ] Right-to-Win score
* [ ] Urgency
* [ ] Confidence
* [ ] Score breakdown
* [ ] Why Hot Now
* [ ] Evidence
* [ ] Orange Business relevance
* [ ] Recommended action
* [ ] Basic filters
* [ ] Refresh button
* [ ] Loading/error/empty states
* [ ] Mock data integration
* [ ] Basic persona selection

## 🟡 Nice to Have

* [ ] Persona-specific dashboards
* [ ] Customer/account overlap
* [ ] Orange capability mapping
* [ ] Opportunity evolution
* [ ] Compare opportunities
* [ ] Advanced filtering

## 🔴 Post-MVP

* [ ] Conversational assistant
* [ ] Custom websites
* [ ] Custom keywords
* [ ] Personalised research
* [ ] Advanced clustering
* [ ] Alerts
* [ ] User accounts
* [ ] Saved opportunities
* [ ] PowerPoint/PDF export
* [ ] Collaboration/comments

---

# 18. Estimated Timeline

A realistic target for the first complete UI MVP is approximately **5–8 working days**, assuming development starts with mock data.

### Day 1 — UX & Structure

* Define user journeys
* Finalise the three personas
* Define wireframes
* Agree on the data structure

### Day 2 — Dashboard

* Dashboard
* Opportunity cards
* Navigation
* Filters

### Day 3 — Opportunity Detail

* Opportunity detail page
* Score breakdown
* Why Hot Now

### Day 4 — Evidence & Orange Fit

* Evidence
* Right to Win
* Orange capabilities
* Recommended actions

### Day 5 — Interaction States

* Refresh flow
* Loading states
* Error states
* Empty states
* Responsive behaviour

### Days 6–8 — Integration & Polish

* Backend/API integration
* Testing
* UI polish
* Bug fixing
* Demo preparation

---

# 19. Key Design Principle

The interface should **not be designed around the AI agents**.

Users do not care whether the backend uses two agents or twenty agents.

They care about:

> **What is the opportunity?**
> **Why now?**
> **How attractive is it?**
> **Can Orange win?**
> **What evidence supports it?**
> **What should I do next?**

The interface succeeds if these six questions can be answered quickly and clearly.

---

# 20. Definition of Done — MVP

The interface can be considered MVP-ready when a user can:

* [ ] Open the Innovation Radar
* [ ] See a ranked list of Opportunity Spaces
* [ ] Filter the opportunities
* [ ] Select an opportunity
* [ ] Understand its attractiveness score
* [ ] Understand its Right-to-Win score
* [ ] See why the opportunity is relevant now
* [ ] See the supporting evidence
* [ ] Understand Orange Business relevance
* [ ] See a recommended next action
* [ ] Switch between Strategist, Sales, and Presales perspectives
* [ ] Refresh the data
* [ ] Understand when the data was last updated
* [ ] Navigate the application without needing to understand the underlying AI pipeline

---

## Final Goal

The MVP should demonstrate that the Innovation Radar is more than a collection of news articles.

It should demonstrate the complete transformation:

```text
External Signals
       ↓
Research & Evidence
       ↓
Opportunity Space
       ↓
Scoring
       ↓
Ranking
       ↓
Explanation
       ↓
Recommended Action
```

The interface is the layer that turns this pipeline into something that **Strategists, Sales Teams, and Presales Teams can actually use.**
