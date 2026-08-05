# Manual review of the 50 submission outputs

This table was reviewed directly from each input and the matching order, item and
payment rows. It is the human decision sheet for `output/`; `reference_output/`
and the LLM audit are not the authority for this review.

Evidence profiles:

- `CUP`: order, item, payment, policy
- `UOP`: order, payment, policy
- `LDS`: order, item, payment, responsible seller, policy
- `LDL`: order, item, payment, policy
- `VSP`: order, item, every payment row, policy
- `ULC`: order, item, payment, policy

| Case | Raw decisive facts | Manual issue | Evidence profile |
| --- | --- | --- | --- |
| EC_001 | delivered late; carrier handoff after seller limit | late_delivery_seller | LDS |
| EC_002 | delivered on time; one reconciled payment | unsupported_late_claim | ULC |
| EC_003 | canceled; payment 109.34 | canceled_order_paid | CUP |
| EC_004 | two payments; reconciled total 211.96 | valid_split_payment | VSP |
| EC_005 | unavailable; payment 1191.50; no item | unavailable_order_paid | UOP |
| EC_006 | two payments; reconciled total 44.38 | valid_split_payment | VSP |
| EC_007 | canceled; payment 56.40 | canceled_order_paid | CUP |
| EC_008 | canceled; payment 250.57; cancellation rule has priority | canceled_order_paid | CUP |
| EC_009 | delivered late; seller handoff timely | late_delivery_logistics | LDL |
| EC_010 | delivered late; seller handoff timely | late_delivery_logistics | LDL |
| EC_011 | unavailable; payment 142.09; no item | unavailable_order_paid | UOP |
| EC_012 | delivered late; seller handoff timely | late_delivery_logistics | LDL |
| EC_013 | unavailable; payment 619.86; no item | unavailable_order_paid | UOP |
| EC_014 | two payments; reconciled total 72.14 | valid_split_payment | VSP |
| EC_015 | canceled; payment 69.49 | canceled_order_paid | CUP |
| EC_016 | delivered late; seller handoff timely | late_delivery_logistics | LDL |
| EC_017 | delivered late; seller handoff timely | late_delivery_logistics | LDL |
| EC_018 | two payments; reconciled total 27.68 | valid_split_payment | VSP |
| EC_019 | unavailable; payment 74.70; no item | unavailable_order_paid | UOP |
| EC_020 | two payments; reconciled total 269.08 | valid_split_payment | VSP |
| EC_021 | canceled; payment 38.86 | canceled_order_paid | CUP |
| EC_022 | delivered late; carrier handoff after seller limit | late_delivery_seller | LDS |
| EC_023 | delivered on time; one reconciled payment | unsupported_late_claim | ULC |
| EC_024 | unavailable; payment 87.08; no item | unavailable_order_paid | UOP |
| EC_025 | three items; two payments; reconciled total 184.32 | valid_split_payment | VSP |
| EC_026 | canceled; payment 142.34 | canceled_order_paid | CUP |
| EC_027 | unavailable; payment 74.70; no item | unavailable_order_paid | UOP |
| EC_028 | unavailable; payment 61.19; no item | unavailable_order_paid | UOP |
| EC_029 | three items; delivered late; all handoffs after seller limit | late_delivery_seller | LDS |
| EC_030 | three payments; reconciled total 25.84 | valid_split_payment | VSP |
| EC_031 | delivered late; seller handoff timely | late_delivery_logistics | LDL |
| EC_032 | two items; delivered on time; payment reconciled | unsupported_late_claim | ULC |
| EC_033 | delivered late; carrier handoff after seller limit | late_delivery_seller | LDS |
| EC_034 | delivered late; carrier handoff after seller limit | late_delivery_seller | LDS |
| EC_035 | delivered on time; one reconciled payment | unsupported_late_claim | ULC |
| EC_036 | unavailable; payment 117.78; no item | unavailable_order_paid | UOP |
| EC_037 | delivered late; carrier handoff after seller limit | late_delivery_seller | LDS |
| EC_038 | two payments; reconciled total 205.26 | valid_split_payment | VSP |
| EC_039 | delivered on time; one reconciled payment | unsupported_late_claim | ULC |
| EC_040 | delivered on time; one reconciled payment | unsupported_late_claim | ULC |
| EC_041 | canceled; payment 53.19 | canceled_order_paid | CUP |
| EC_042 | delivered on time; one reconciled payment | unsupported_late_claim | ULC |
| EC_043 | delivered late; carrier handoff after seller limit | late_delivery_seller | LDS |
| EC_044 | delivered late; carrier handoff after seller limit | late_delivery_seller | LDS |
| EC_045 | canceled; payment 69.07 | canceled_order_paid | CUP |
| EC_046 | two payments; reconciled total 126.01 | valid_split_payment | VSP |
| EC_047 | delivered on time; one reconciled payment | unsupported_late_claim | ULC |
| EC_048 | delivered on time; one reconciled payment | unsupported_late_claim | ULC |
| EC_049 | delivered late; seller handoff timely | late_delivery_logistics | LDL |
| EC_050 | delivered late; seller handoff timely | late_delivery_logistics | LDL |

Manual issue counts: CUP 8, UOP 8, LDS 8, LDL 8, VSP 9, ULC 9.
