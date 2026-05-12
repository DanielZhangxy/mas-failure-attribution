import json
import datetime
from pathlib import Path
from typing import Dict, Any, Optional, Literal, List
from autogen import UserProxyAgent, ConversableAgent
from autogen.agentchat.contrib.captainagent import CaptainAgent
from ..base_adapter import BaseAdapter
from ..middleware import patch_with_middlewares
from adapter.CaptainAgent.middlewares.think import ThinkMiddleware
from adapter.CaptainAgent.middlewares.observe import ObserveMiddleware


def serialize_state(state: Dict[str, Any], path: Path, filename: str = "captain_state"):
    state_file = path / f"{filename}.json"
    with open(state_file, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def deserialize_state(path: Path, filename: str = "captain_state") -> Optional[Dict[str, Any]]:
    state_file = path / f"{filename}.json"
    if state_file.exists():
        with open(state_file, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


class CaptainAgentAdapter(BaseAdapter):
    def __init__(
        self,
        model: str = None,
        api_key: str = None,
        base_url: str = None,
        temp: float = 0.2,
        max_round: int = 20,
        human_input_mode: Literal["ALWAYS", "TERMINATE", "NEVER"] = "NEVER"
    ):
        self.llm_config = None
        if model and api_key and base_url:
            self.llm_config = {
                "config_list": [
                    {
                        "model": model,
                        "api_key": api_key,
                        "base_url": base_url
                    }
                ],
                "temperature": temp,
                "timeout": 300,
            }

        self.captain = None
        self.user_proxy = None
        self.max_round = max_round
        self.human_input_mode = human_input_mode
        self.workspace = None
        self.conversation_history = []
        self.task_idea = None
        self.default_filename = "captain_state"
        self.registered_agents = []

    def run_backend(
        self,
        idea: str,
        workspace: Path,
        recovery: Path = None,
        monitor = None,
        enable_lint: bool = True,
    ):
        self.workspace = workspace
        self.task_idea = idea

        workspace.mkdir(parents=True, exist_ok=True)

        if recovery and recovery.exists():
            self._handle_recovery(recovery, monitor)

        self.user_proxy = UserProxyAgent(
            name="User",
            human_input_mode=self.human_input_mode,
            max_consecutive_auto_reply=self.max_round * 3,
            code_execution_config={
                "work_dir": str(workspace),
                "use_docker": False,
                "timeout": 300,
            } if enable_lint else False,
        )

        self.captain = CaptainAgent(
            name="Captain",
            llm_config=self.llm_config,
            code_execution_config={
                "work_dir": str(workspace),
                "use_docker": False,
            } if enable_lint else False,
            system_message="""You are a task coordinator. Analyze requirements, decompose tasks, dynamically create expert agents, and coordinate them to complete objectives.""",
        )

        if monitor:
            self._apply_monitor_middleware(monitor)

        self.user_proxy.initiate_chat(
            self.captain,
            message=f"Task: {idea}\nWorkspace: {workspace}\nMax rounds: {self.max_round}",
            max_turns=self.max_round,
        )

        self._capture_conversation()

        return str(workspace)

    def save_current_state(self, path: Path):
        if not self.captain:
            return

        path.mkdir(parents=True, exist_ok=True)

        state = {
            "adapter_type": "CaptainAgentAdapter",
            "captain_name": self.captain.name,
            "workspace": str(self.workspace) if self.workspace else "",
            "task_idea": self.task_idea or "",
            "max_round": self.max_round,
            "human_input_mode": self.human_input_mode,
            "saved_at": datetime.datetime.now().isoformat(),
            "conversation_history": self.conversation_history,
        }

        if hasattr(self.captain, '_agents') and self.captain._agents:
            dynamic_agents = []
            for agent_name, agent in self.captain._agents.items():
                if agent != self.captain:
                    agent_info = {
                        "name": agent_name,
                        "type": type(agent).__name__,
                    }
                    if hasattr(agent, 'system_message'):
                        agent_info["system_message"] = agent.system_message
                    dynamic_agents.append(agent_info)
            state["dynamic_agents"] = dynamic_agents

        serialize_state(state, path, self.default_filename)

    def get_prompt_map(self) -> Dict[str, str]:
        prompts = {}

        if self.captain and hasattr(self.captain, 'system_message'):
            prompts[self.captain.name] = self.captain.system_message

        if hasattr(self, 'captain') and self.captain and hasattr(self.captain, '_agents'):
            for agent_name, agent in self.captain._agents.items():
                if agent != self.captain and hasattr(agent, 'system_message'):
                    prompts[agent_name] = agent.system_message

        if not prompts:
            prompts = {
                "Captain": "Task coordinator that dynamically creates and manages expert agents."
            }

        return prompts

    def _handle_recovery(self, recovery: Path, monitor):
        state = deserialize_state(recovery, self.default_filename)
        if state:
            if monitor and hasattr(monitor, 'history'):
                pass

    def _apply_monitor_middleware(self, monitor):
        if not monitor:
            return

        agents_to_monitor = self._get_all_agents()

        for agent in agents_to_monitor:
            if not isinstance(agent, ConversableAgent):
                continue

            # Apply ThinkMiddleware to generate_reply
            patch_with_middlewares(
                agent,
                "generate_reply",
                [ThinkMiddleware(monitor, agent.name)]
            )

            # Apply ObserveMiddleware to _observe
            patch_with_middlewares(
                agent,
                "_observe",
                [ObserveMiddleware(monitor)]
            )

    def _get_all_agents(self) -> List:
        agents = []

        if self.captain:
            agents.append(self.captain)

        if self.user_proxy:
            agents.append(self.user_proxy)

        if hasattr(self.captain, '_agents') and self.captain._agents:
            for agent_name, agent in self.captain._agents.items():
                if agent not in agents:
                    agents.append(agent)

        return agents

    def _capture_conversation(self):
        self.conversation_history = []

        if hasattr(self.captain, 'chat_messages') and self.captain.chat_messages:
            for agent, messages in self.captain.chat_messages.items():
                agent_name = agent.name if hasattr(agent, 'name') else str(agent)
                for msg in messages:
                    if isinstance(msg, dict):
                        self.conversation_history.append({
                            "agent": agent_name,
                            "content": msg.get("content", ""),
                            "role": msg.get("role", ""),
                        })