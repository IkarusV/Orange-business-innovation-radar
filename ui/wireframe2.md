# Innovation Radar — MVP Wireframes

This document describes the first wireframe version of the Innovation Radar interface.

The goal is not to define the final visual design yet, but to define:

- What screens exist
- What information is displayed
- Where the main actions are
- How users move through the application
- How the interface adapts to the three target users

The three target users are:

- **Strategists & Innovators**
- **Sales Teams**
- **Presales & Proposal Teams**

---

# 1. Main User Flow

The MVP should follow a simple journey:

```text
User opens Innovation Radar
          ↓
Selects user perspective
          ↓
Views Opportunity Dashboard
          ↓
Applies filters
          ↓
Browses Opportunity Spaces
          ↓
Selects an Opportunity Space
          ↓
Views Opportunity Details
          ↓
Reviews scores and evidence
          ↓
Understands Orange Business relevance
          ↓
Receives a recommended next action

# Opportunity Dashboard

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ORANGE BUSINESS — INNOVATION RADAR                         │
│                                                             │
│  [ Strategist ]   [ Sales ]   [ Presales ]                  │
│                                                             │
│                                      [ ↻ Refresh Data ]      │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  FILTERS                                                    │
│                                                             │
│  [ Vertical ▼ ]  [ Technology ▼ ]  [ Urgency ▼ ]           │
│  [ Confidence ▼ ]                         [ Min Score ▼ ]   │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  TOP OPPORTUNITIES                                          │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Banking × WAN Security × Network Analytics            │  │
│  │                                                       │  │
│  │  8.8 / 10      NOW      HIGH CONFIDENCE              │  │
│  │                                                       │  │
│  │  Why hot now:                                         │  │
│  │  Increasing cybersecurity investment and regulatory   │  │
│  │  pressure.                                            │  │
│  │                                                       │  │
│  │  Orange Right to Win: 8.3 / 10                       │  │
│  │                                                       │  │
│  │                         [ View Opportunity → ]         │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Government × Sovereign Cloud × AI                     │  │
│  │                                                       │  │
│  │  8.6 / 10      NOW      HIGH CONFIDENCE              │  │
│  │                                                       │  │
│  │  Why hot now:                                         │  │
│  │  Growing demand for sovereign AI and trusted cloud.  │  │
│  │                                                       │  │
│  │  Orange Right to Win: 9.2 / 10                       │  │
│  │                                                       │  │
│  │                         [ View Opportunity → ]         │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
│  ┌───────────────────────────────────────────────────────┐  │
│  │ Insurance × Claims × Agentic AI                       │  │
│  │                                                       │  │
│  │  8.2 / 10      NEXT      MEDIUM CONFIDENCE           │  │
│  │                                                       │  │
│  │                         [ View Opportunity → ]         │  │
│  └───────────────────────────────────────────────────────┘  │
│                                                             │
└─────────────────────────────────────────────────────────────┘


# Opportunity Detail

┌─────────────────────────────────────────────────────────────┐
│                                                             │
│  ← Back to Opportunities                                    │
│                                                             │
│  BANKING × WAN SECURITY × NETWORK ANALYTICS                 │
│                                                             │
│  8.8 / 10        NOW        HIGH CONFIDENCE                 │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  WHY HOT NOW                                                │
│                                                             │
│  Increasing cybersecurity investment, regulatory pressure   │
│  and recent customer deployments are creating demand for    │
│  network security analytics in banking.                     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  WHY IT MATTERS                                            │
│                                                             │
│  Customer value:                                             │
│  Better visibility, security monitoring and risk detection. │
│                                                             │
│  Orange Business relevance:                                  │
│  Strong alignment with cybersecurity and secure             │
│  connectivity capabilities.                                  │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  MARKET ATTRACTIVENESS                                      │
│                                                             │
│  Market Signal Strength        9.1 / 10                     │
│  Source Diversity              8.1 / 10                     │
│  Evidence Quality              8.4 / 10                     │
│  Novelty / Momentum             9.0 / 10                     │
│  Strategic Relevance            9.2 / 10                     │
│                                                             │
│  ─────────────────────────────────────────                  │
│  ATTRACTIVENESS                8.8 / 10                     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ORANGE BUSINESS — RIGHT TO WIN                             │
│                                                             │
│  Offering / Asset Fit           9.2 / 10                     │
│  Customer Overlap               8.5 / 10                     │
│  Reference Cases                7.5 / 10                     │
│  Partner Readiness              8.0 / 10                     │
│                                                             │
│  ─────────────────────────────────────────                  │
│  RIGHT TO WIN                   8.3 / 10                     │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  EVIDENCE                                                   │
│                                                             │
│  [ REGULATION ]                                             │
│  EU regulation introduces new requirements...               │
│  Date: 2026-05-12                                           │
│  Source: EUR-Lex                              [ Open → ]      │
│                                                             │
│  [ MARKET TREND ]                                           │
│  Cybersecurity investment continues to increase...           │
│  Date: 2026-06-20                                           │
│  Source: Example Source                         [ Open → ]    │
│                                                             │
│  [ PROOF SIGNAL ]                                           │
│  Named customer deployment...                                │
│  Date: 2026-07-02                                           │
│  Source: Example Source                         [ Open → ]    │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  ORANGE BUSINESS CAPABILITIES                               │
│                                                             │
│  ✓ Relevant cybersecurity offering                          │
│  ✓ Existing banking customers                               │
│  ✓ Technology partner available                             │
│  ✓ Relevant reference case                                  │
│  △ Additional technical capability to assess                │
│                                                             │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  RECOMMENDED NEXT ACTION                                    │
│                                                             │
│  Organise a security visibility workshop with relevant      │
│  banking accounts.                                          │
│                                                             │
│                         [ Take Action → ]                    │
│                                                             │
└─────────────────────────────────────────────────────────────┘

# User Perspective

## Strategist Perspective

┌──────────────────────────────────────────────┐
│ STRATEGIST VIEW                              │
│                                              │
│ Opportunity                                  │
│ Banking × WAN Security × Analytics           │
│                                              │
│ Attractiveness            8.8 / 10           │
│ Urgency                   NOW                │
│ Confidence                HIGH               │
│                                              │
│ Strategic Relevance       9.2 / 10           │
│ Market Momentum           9.0 / 10           │
│                                              │
│ Recommended Action                           │
│                                              │
│ → Assess as a growth opportunity              │
│ → Monitor market development                  │
│ → Identify capability gaps                    │
│ → Assess potential partners                   │
└──────────────────────────────────────────────┘

## Sales Perspective

┌──────────────────────────────────────────────┐
│ SALES VIEW                                   │
│                                              │
│ Opportunity                                  │
│ Banking × WAN Security × Analytics           │
│                                              │
│ Attractiveness            8.8 / 10           │
│ Urgency                   NOW                │
│ Confidence                HIGH               │
│                                              │
│ Customer Relevance                            │
│                                              │
│ Existing banking accounts: 12               │
│ Relevant buying signals: 3                  │
│ Existing reference cases: 2                 │
│                                              │
│ Recommended Action                           │
│                                              │
│ → Identify relevant banking accounts         │
│ → Open a customer conversation                │
│ → Organise a customer workshop                │
│ → Use existing reference cases                │
└──────────────────────────────────────────────┘

## Presale Perspective

┌──────────────────────────────────────────────┐
│ PRESALES VIEW                                │
│                                              │
│ Opportunity                                  │
│ Banking × WAN Security × Analytics           │
│                                              │
│ Technology                                   │
│ Network Security Analytics                   │
│                                              │
│ Orange Capabilities                          │
│                                              │
│ ✓ Existing security offering                │
│ ✓ Relevant infrastructure                   │
│ ✓ Technology partner                        │
│ ✓ Reference case                            │
│ △ Capability gap to investigate              │
│                                              │
│ Right to Win              8.3 / 10           │
│                                              │
│ Recommended Action                           │
│                                              │
│ → Identify relevant Orange offerings         │
│ → Perform technical deep-dive                │
│ → Assess partner capabilities                │
│ → Reuse existing reference architecture     │
└──────────────────────────────────────────────┘

# Overall MVP Navigation

                         ┌───────────────┐
                         │   DASHBOARD   │
                         │               │
                         │ Opportunities │
                         │ Filters       │
                         │ Personas      │
                         │ Refresh       │
                         └───────┬───────┘
                                 │
                                 │ Click opportunity
                                 ▼
                    ┌────────────────────────┐
                    │ OPPORTUNITY DETAIL     │
                    │                        │
                    │ Why Hot Now             │
                    │ Why It Matters          │
                    │ Attractiveness           │
                    │ Right to Win            │
                    │ Evidence                │
                    │ Orange Capabilities     │
                    │ Recommended Action      │
                    └────────────┬───────────┘
                                 │
                                 │ User perspective
                                 ▼
                    ┌────────────────────────┐
                    │ PERSONA PERSPECTIVE    │
                    │                        │
                    │ Strategist              │
                    │ Sales                   │
                    │ Presales                │
                    │                        │
                    │ Different focus/actions │
                    └────────────────────────┘