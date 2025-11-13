import asyncio
import os

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_agentchat.ui import Console
from autogen_ext.models.openai import OpenAIChatCompletionClient
from autogen_ext.tools.mcp import McpWorkbench, StdioServerParams
from mcp import StdioServerParameters

os.environ[
    "OPENAI_API_KEY"] = "OpenAIToken"
os.environ[
    "JIRA_API_TOKEN"] = "JIRA Board Token"
os.environ["JIRA_URL"] = "Jira board"
os.environ["JIRA_USERNAME"] = "username"
os.environ["JIRA_PROJECTS_FILTER"] = "board code"

shared_state = {
    "execution_results": {
        "Bug_ID":"Result"
    }
}


async def main():
    client_model = OpenAIChatCompletionClient(model="gpt-4o")

    jira_server_Params = StdioServerParams(command="docker",
                                           args=[
                                               "run", "-i", "--rm",
                                               "--dns", "8.8.8.8", "--dns", "1.1.1.1",
                                               "--network", "host",
                                               "-e", f"JIRA_URL={os.environ['JIRA_URL']}",
                                               "-e", f"JIRA_USERNAME={os.environ['JIRA_USERNAME']}",
                                               "-e", f"JIRA_API_TOKEN={os.environ['JIRA_API_TOKEN']}",
                                               "-e", f"JIRA_PROJECTS_FILTER={os.environ['JIRA_PROJECTS_FILTER']}",
                                               "--entrypoint", "mcp-atlassian",
                                               "ghcr.io/sooperset/mcp-atlassian:latest"
                                           ]
                                           )

    Jira_workbench = McpWorkbench(jira_server_Params)

    playwright_server_Params = StdioServerParams(command="npx",
                                                 args=[
                                                     "@playwright/mcp@latest"
                                                 ]
                                                 )

    Playwright_workbench = McpWorkbench(playwright_server_Params)

    async with Jira_workbench as jira_wb, Playwright_workbench as playwright_wb:
        bugAnalyst = AssistantAgent(name="BugAnalyst", model_client=client_model,
                                    workbench=jira_wb,
                                    system_message=("You are a Bug Analysis Agent.\n"
                                                    "Your task is to query Jira for all issues in the 'Resolved' state, read carefully the descriptions, "
                                                    "and generate a Sanity Test Plan for each issue. Following all the steps are robust\n"
                                                    "After all test plans are created and stored, write exactly: **'HANDOFF TO AUTOMATION'**"
                                                    "to signal the PlaywrightAgent to begin automated testing.\n"
                                                    "Do not hand off early — only after every Sanity Test plan is complete and saved.\n"
                                                    "Please a request complete Bug analysis slowly do not rush and do not trigger JiraAnalyst call during Bug Analysis\n"))

        automationanalyst = AssistantAgent(name="PlaywrightAgent", model_client=client_model, workbench=playwright_wb,
                                           system_message=("You are a Playwright Automation Agent.\n\n"
                                                           "Execute each step of the Sanity Test Plan flow for every bug.\n"
                                                           "Convert the user flow from BugAnalyst into executable Playwright commands and run them reliably.\n\n"
                                                           "🧪 **Validation Rules:**\n"
                                                           "- For each action, validate the expected result as defined in the Sanity Test Plan.\n"
                                                           "- Use `page.text_content()`, `page.locator().is_visible()`, or assertions to confirm outcomes.\n"
                                                           "- Store a result summary for each BUG_KEY in shared_state['execution_results'] as:\n"
                                                           "Example: shared_state['execution_results'] = { 'BUG-123': 'Pass', 'BUG-124': 'Fail' }."
                                                           "Take time to execute each of the steps of the test plan do not rush to complete"
                                                           " Once all the steps are verified close the browser \n"
                                                           "Please do not Handoff unless all the steps are executed.\n"
                                                           "Retry if timeout error occurs.\n"

                                                           "🧭 **Completion Behavior:**\n"
                                                           "- When all steps for a bug’s Sanity Test Plan are executed and validated, write exactly:\n"
                                                           "  **'VERIFICATION COMPLETE'** to signal that automation is complete. and then Handoff to JIRA ANALYST\n"
                                                           "- Do not hand off until all steps are executed with proper waits and validations.\n"
                                                           "- Be patient: it is better to execute slowly and accurately than to rush and fail due to timeouts.\n"
                                                           "Do not add any comment in JIRA bug unless the execution of all the steps are completed.\n"
                                                            "Provide all the execution steps as logs"

                                                           ))

        jiraanalyst = AssistantAgent(name="JiraAnalyst", model_client=client_model,
                                     workbench=jira_wb,
                                     system_message=(
                                         "You are a Jira expert.Once the execution is completed then only you come into action. Read execution results from shared_state['execution_results'] for each of the bug.\n"
                                         "For each bug:\n"
                                         "- Only act if shared_state['execution_results'] exists and contains a valid result example Pass or Fail.\n"
                                         "- If Bug_ID == 'Pass' → change the workflow of the BUG in JIRA IR board  to CLOSED.\n"
                                         "- If Bug_ID == 'Fail' → change the workflow of the BUG in JIRA IR board to IN PROGRESS.\n"
                                         "Never close or modify an issue unless PlaywrightAgent confirms a valid result like 'Pass' or 'Fail'.\n"
                                         "After updating all valid bugs, confirm **'VALIDATION COMPLETE'** share the logs. \n"))

        team = RoundRobinGroupChat(participants=[bugAnalyst, automationanalyst, jiraanalyst],
                                   termination_condition=TextMentionTermination('VALIDATION COMPLETE'))

        await Console(team.run_stream(
            task="BugAnalyst: Analyze resolved bugs in IR project and populate shared_state['test_plan']. \n"
                 "1. Then design a stable user flow that can be used for sanity test \n"
                 "2. Use REAL urls : 'url to validate' \n"

                 "PlaywrightAgent: Execute test plan from shared_state['test_plan'] and update shared_state['execution_results']. \n"

                 "JiraAnalyst: Read shared_state['execution_results'] and update Jira workflow accordingly.\n"))


asyncio.run(main())
