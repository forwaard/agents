from utils import get_key_history, get_embedding
import torch
from LLMs.base_LLM import *
from Memorys import Memory


class Environment:
    def __init__(self, config) -> None:
        self.shared_memory = {"long_term_memory": [], "short_term_memory": None}
        self.agents = None

        self.summary_system_prompt = {}
        self.summary_last_prompt = {}
        self.environment_prompt = {}
        self.environment_type = config["environment_type"] if "environment_type" in config else "cooperate"
        self.current_chat_history_idx = 0
        self.LLMs = {}
        
        # 初始化每个state 的summary 方法
        # Initialize the summary method for each state
        for state_name, state_dict in config["states"].items():
            if state_name != "end_state":
                self.summary_system_prompt[state_name] = (
                    state_dict["summary_system_prompt"]
                    if "summary_system_prompt" in state_dict
                    else "\nYour task is to summarize the historical dialogue records according to the current scene, and summarize the most important information"
                )

                self.summary_last_prompt[state_name] = (
                    state_dict["summary_last_prompt"]
                    if "summary_last_prompt" in state_dict
                    else "Please make a summary based on the historical chat records, the output format is history summary: \{your summary content\} "
                )

                self.environment_prompt[state_name] = (
                    state_dict["environment_prompt"]
                    if "environment_prompt" in state_dict
                    else " "
                )
                LLM_type = (
                    state_dict["LLM_type"] if "LLM_type" in state_dict else "OpenAI"
                )
                if LLM_type == "OpenAI":
                    if "LLM" in state_dict:
                        self.LLMs[state_name] = OpenAILLM(**state_dict["LLM"])
                    else:
                        self.LLMs[state_name] = OpenAILLM(model = "gpt-3.5-turbo-16k-0613",temperature=0.3,log_path=f"logs/{state_name}")
        self.roles_to_names = None
        self.names_to_roles = None

    @classmethod
    def from_config(cls, config_path):
        with open(config_path) as f:
            config = json.load(f)
        return cls(config)

    def summary(self, current_state):
        """
        Summarize the situation in the current environment every once in a while
        """
        MAX_CHAT_HISTORY = eval(os.environ["MAX_CHAT_HISTORY"])
        current_state_name = current_state.name

        query = self.shared_memory["long_term_memory"][-1]
        key_history = get_key_history(
            query,
            self.shared_memory["long_term_memory"][:-1],
            self.shared_memory["chat_embeddings"][:-1],
        )

        relevant_history = Memory.get_chat_history(key_history)
        chat_history = Memory.get_chat_history(
            self.shared_memory["long_term_memory"][-MAX_CHAT_HISTORY + 1 :]
        )
        summary = self.shared_memory["short_term_memory"]
        
        # current_memory = summary + chat history + relevant history
        current_memory = f"The information you need to know is as follows:\n<information>\n\
            The summary of the previous dialogue history is:<summary>\n{summary}\n.\
            The latest conversation record is as follows:\n<hisroty> {chat_history}\n<history>,\
            the relevant chat history you may need is:<relevant>{relevant_history}<relevant>"

        # system prompt = environment prompt + current memory + system prompt
        system_prompt = (
            self.environment_prompt[current_state_name]
            + current_memory
            + self.summary_system_prompt[current_state_name]
        )
        response = self.LLMs[current_state_name].get_response(None, system_prompt, stream=False)
        return response

    def update_memory(self, memory, current_state):
        """
        update chat embbedings and long term memory,short term memory,agents long term memory
        """
        MAX_CHAT_HISTORY = eval(os.environ["MAX_CHAT_HISTORY"])
        self.shared_memory["long_term_memory"].append(memory)
        current_embedding = get_embedding(memory.content)
        if "chat_embeddings" not in self.shared_memory:
            self.shared_memory["chat_embeddings"] = current_embedding
        else:
            self.shared_memory["chat_embeddings"] = torch.cat(
                [self.shared_memory["chat_embeddings"], current_embedding], dim=0
            )
        if len(self.shared_memory["long_term_memory"]) % MAX_CHAT_HISTORY == 0:
            summary = self.summary(current_state)
            self.shared_memory["short_term_memory"] = summary

        self.agents[memory.send_name].update_memory(memory)
