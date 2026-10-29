# Global Codex instructions

## Change planning and approval

Before taking action or completing an implementation plan, evaluate your understanding of the task constraints, architecture, context, and desired output. 

You must be at least **95% confident** in what needs to be done. If your confidence is below 95%:
- Pause immediately before guessing implementation details or making unverified assumptions.
- Identify the specific ambiguities, missing context, or assumptions.
- Ask targeted questions to gather the precise information required to reach 95% confidence before presenting a plan or executing code.

Before implementing any change expected to modify more than two files:

1. Present a concrete implementation plan to the user.
2. Wait for the user to review and explicitly approve the plan.
3. Begin implementation only after receiving that approval.

## Work plans and agents

1. When creating a work plan, state whether multiple agents would help and briefly explain why.
2. Recommend a model for each agent in the plan, including the primary agent, with a brief reason for each choice.

## Editing discipline

Do not run formatters or linters during implementation. Keep changes minimal,
focused, and easy to review.
