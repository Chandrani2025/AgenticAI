**Muti Agentic Workflow for validating Bug in JIRA board and according update the Defect workflow based on Playwright Execution result**

1. Using OpenAI LLM Model (gpt-4o) as Client Model .
2. JIRA MCP Server for JIRA board analysis to pull up the bugs in Resolved state and provide the Sanity Test Plan with proper steps for execution and reproduce the issue as well as after Playwright automation execution update the bug to InProgress or Closed based on execution result.
3. Playwright MCP Server for execution the Manual Test Steps.
4. Also on updating Bug adding a comment as it is validated or not.
