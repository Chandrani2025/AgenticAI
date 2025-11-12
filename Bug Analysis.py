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
    "test_plan": {},
    "execution_results": {}
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
                                                    "Your task is to query Jira for all issues in the 'Resolved' state, analyze their descriptions, "
                                                    "and generate a Sanity Test Plan for each issue.\n"
                                                    "Store the generated plan in shared_state['test_plan'] as JSON in the format:\n"
                                                    "{'BUG_KEY': [{'step': <n>, 'action': <text>, 'expected_result': <text>}, ...]}\n"
                                                    "After all test plans are created and stored, write exactly: **'HANDOFF TO AUTOMATION'**"
                                                    "to signal the PlaywrightAgent to begin automated testing.\n"
                                                    "Do not hand off early — only after every bug's plan is complete and saved.\n"
                                                    "Do not trigger JiraAnalyst call during Bug Analysis"))

        automationanalyst = AssistantAgent(name="PlaywrightAgent", model_client=client_model, workbench=playwright_wb,
                                           system_message=("You are a Playwright Automation Agent.\n\n"
                                                           "Execute each step of the Sanity Test Plan flow for every BUG_KEY provided.\n"
                                                           "Convert the user flow from BugAnalyst into executable Playwright commands and run them reliably.\n\n"

                                                           "💡 **Execution Guidelines:**\n"
                                                           "- Before performing any action (click, type, validate), always wait for the target element using:\n"
                                                           "  `page.wait_for_selector(<selector>, timeout=15000)` or a similar reliable locator.\n"
                                                           "- For buttons or links, prefer role-based locators (e.g., `page.get_by_role('button', name='Login')`) over text or index-based locators.\n"
                                                           "- Use `no_wait_after=True` if the click does not cause navigation.\n"
                                                           "- Increase timeouts up to 15 seconds if the page or element is slow.\n"
                                                           "- Capture screenshots after key steps (login, navigation, validation, error).\n"
                                                           "- If a step times out, retry it once after waiting an additional 3 seconds before failing.\n\n"

                                                           "🧪 **Validation Rules:**\n"
                                                           "- After each action, validate the expected result as defined in the Sanity Test Plan.\n"
                                                           "- Use `page.text_content()`, `page.locator().is_visible()`, or assertions to confirm outcomes.\n"
                                                           "- Log 'Step Passed' or 'Step Failed' clearly, including the step number and element.\n"
                                                           "- Store a result summary for each BUG_KEY in shared_state['execution_results'] as:\n"
                                                           "  `{'BUG_KEY': 'Passed' or 'Fail'}`\n\n"

                                                           "🧭 **Completion Behavior:**\n"
                                                           "- When all steps for a bug’s Sanity Test Plan are executed and validated, write exactly:\n"
                                                           "  **'HANDOFF TO JIRA'** to signal that automation is complete.\n"
                                                           "- Do not hand off until all steps are executed with proper waits and validations.\n"
                                                           "- Be patient: it is better to execute slowly and accurately than to rush and fail due to timeouts.\n"

                                                           ))

        jiraanalyst = AssistantAgent(name="JiraAnalyst", model_client=client_model,
                                     workbench=jira_wb,
                                     system_message=(
                                         "You are a Jira expert. Read execution results from shared_state['execution_results'].\n"
                                         "For each bug:\n"
                                         "- If Passed → mark status as CLOSED\n"
                                         "- If Fail → mark status as IN PROGRESS\n"
                                         "After updating all bugs, confirm **'VALIDATION COMPLETE'.**"))

        team = RoundRobinGroupChat(participants=[bugAnalyst, automationanalyst, jiraanalyst],
                                   termination_condition=TextMentionTermination('VALIDATION COMPLETE'))

        await Console(team.run_stream(
            task="BugAnalyst: Analyze resolved bugs in IR project and populate shared_state['test_plan']. \n"
                 "1. Then design a stable user flow that can be used for sanity test \n"
                 "2. Use REAL urls : 'url to validate' \n"

                 "PlaywrightAgent: Execute test plan from shared_state['test_plan'] and update shared_state['execution_results']. \n"

                 "JiraAnalyst: Read shared_state['execution_results'] and update Jira workflow accordingly.\n"))


asyncio.run(main())
