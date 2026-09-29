"""
Camel-AI tool strict schema monkey patch.
Removes `"strict": True` and handles `tool_choice: "auto"` for compatibility with local LLMs (e.g., vLLM).
Supports both OpenAIModel and OpenAICompatibleModel.
"""
import logging

logger = logging.getLogger('mirofish.camel_patch')

# 0. Patch tiktoken and camel.utils.token_counting to prevent network hanging
# tiktoken attempts to download bpe files (e.g. o200k_base.tiktoken) from Azure blob storage
# without a timeout, which causes permanent process hang in offline or restricted environments.
try:
    class SafeOfflineEncoding:
        """Offline mock encoding to prevent tiktoken from hanging on remote downloads."""
        def __init__(self, name="cl100k_base"):
            self.name = name

        def encode(self, text: str, disallowed_special=(), allowed_special=None):
            if not isinstance(text, str):
                text = str(text)
            # Safe character/byte token estimate (fast, offline, no remote request)
            return list(text.encode("utf-8", errors="ignore"))

        def decode(self, token_ids: list):
            if isinstance(token_ids, list):
                return bytes([t % 256 for t in token_ids if isinstance(t, int)]).decode("utf-8", errors="ignore")
            return ""

    _offline_encoding_instance = SafeOfflineEncoding()

    import camel.utils.token_counting
    camel.utils.token_counting.get_model_encoding = lambda val: _offline_encoding_instance
    logger.info("Successfully monkey-patched camel.utils.token_counting.get_model_encoding for offline safety.")

    try:
        import tiktoken
        tiktoken.get_encoding = lambda encoding_name: _offline_encoding_instance
        tiktoken.encoding_for_model = lambda model_name: _offline_encoding_instance
        logger.info("Successfully monkey-patched tiktoken.get_encoding and encoding_for_model.")
    except Exception as e_tiktoken:
        logger.debug(f"tiktoken not imported or patch skipped: {e_tiktoken}")

except Exception as e:
    logger.warning(f"Failed to monkey patch token counting: {e}")

# 1. Patch FunctionTool to remove strict validation parameter
try:
    import camel.toolkits.function_tool
    original_get_openai_tool_schema = camel.toolkits.function_tool.get_openai_tool_schema
    
    def patched_get_openai_tool_schema(*args, **kwargs):
        schema = original_get_openai_tool_schema(*args, **kwargs)
        if isinstance(schema, dict) and "function" in schema:
            schema["function"].pop("strict", None)
        return schema
        
    camel.toolkits.function_tool.get_openai_tool_schema = patched_get_openai_tool_schema
    logger.info("Successfully monkey-patched camel.toolkits.function_tool to remove 'strict': True.")
except Exception as e:
    logger.warning(f"Failed to monkey patch camel tool strictness: {e}")

# 2. Patch OpenAIModel.__init__ and _sanitize_config
try:
    import camel.models.openai_model
    original_openai_init = camel.models.openai_model.OpenAIModel.__init__
    
    def patched_openai_init(self, *args, **kwargs):
        original_openai_init(self, *args, **kwargs)
        if isinstance(self.model_config_dict, dict):
            if self.model_config_dict.get("tool_choice") == "auto":
                self.model_config_dict.pop("tool_choice", None)
                
    camel.models.openai_model.OpenAIModel.__init__ = patched_openai_init
    
    # Keep the _sanitize_config patch as double-safety
    original_sanitize_config = camel.models.openai_model.OpenAIModel._sanitize_config
    def patched_sanitize_config(self, config_dict):
        sanitized = original_sanitize_config(self, config_dict)
        if isinstance(sanitized, dict):
            if sanitized.get("tool_choice") == "auto":
                sanitized.pop("tool_choice", None)
        return sanitized
    camel.models.openai_model.OpenAIModel._sanitize_config = patched_sanitize_config
    
    logger.info("Successfully monkey-patched camel.models.openai_model.OpenAIModel.")
except Exception as e:
    logger.warning(f"Failed to monkey patch OpenAIModel: {e}")

# 3. Patch OpenAICompatibleModel.__init__ to remove tool_choice='auto'
try:
    import camel.models.openai_compatible_model
    original_compatible_init = camel.models.openai_compatible_model.OpenAICompatibleModel.__init__
    
    def patched_compatible_init(self, *args, **kwargs):
        original_compatible_init(self, *args, **kwargs)
        if isinstance(self.model_config_dict, dict):
            if self.model_config_dict.get("tool_choice") == "auto":
                self.model_config_dict.pop("tool_choice", None)
                
    camel.models.openai_compatible_model.OpenAICompatibleModel.__init__ = patched_compatible_init
    logger.info("Successfully monkey-patched camel.models.openai_compatible_model.OpenAICompatibleModel.")
except Exception as e:
    logger.warning(f"Failed to monkey patch OpenAICompatibleModel: {e}")

# 4. Patch SocialAgent to bypass tool calling entirely and use JSON prompts instead
try:
    import json
    import re
    from camel.messages import BaseMessage
    import oasis.social_agent.agent
    
    async def patched_perform_action_by_llm(self):
        # Build tools schema string
        tools_schema = []
        if hasattr(self, 'action_tools'):
            for tool in self.action_tools:
                if hasattr(tool, 'get_openai_tool_schema'):
                    tools_schema.append(tool.get_openai_tool_schema())
        
        # 查詢 Agent 自身歷史發文記憶 (Self-Action Memory)
        self_memory_prompt = ""
        try:
            import os
            import sqlite3
            import glob
            db_path = getattr(self, 'db_path', None)
            if not db_path:
                db_path = getattr(getattr(getattr(self, 'env', None), 'platform', None), 'db_path', None)
            # 優先檢查當前工作目錄 (子程序 cwd 通常在 simulation 目錄下)
            if not db_path:
                for db_name in ["twitter_simulation.db", "reddit_simulation.db"]:
                    if os.path.exists(db_name):
                        db_path = os.path.abspath(db_name)
                        break
            if not db_path:
                local_dbs = glob.glob("*_simulation.db")
                if local_dbs:
                    db_path = os.path.abspath(local_dbs[0])
            if not db_path:
                candidate_dbs = sorted(
                    glob.glob("backend/uploads/simulations/*/*_simulation.db") + 
                    glob.glob("uploads/simulations/*/*_simulation.db"),
                    key=os.path.getmtime,
                    reverse=True
                )
                if candidate_dbs:
                    db_path = candidate_dbs[0]

            if db_path and os.path.exists(db_path):
                conn = sqlite3.connect(db_path)
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT post_id, content FROM post WHERE user_id = ? ORDER BY post_id DESC LIMIT 3",
                    (self.social_agent_id,)
                )
                past_posts = cursor.fetchall()
                conn.close()
                if past_posts:
                    post_lines = "\n".join([f"- [歷史公開發布 #{pid}]: 「{txt}」" for pid, txt in reversed(past_posts)])
                    self_memory_prompt = (
                        f"【你本人過去在社群公開發布的言論與重大立場聲明（核心約束）】：\n"
                        f"{post_lines}\n"
                        f"【行為連貫性約束】：身為公眾官方實體，你本輪所有的發言、按讚、轉發、引用評論等動作，必須嚴格維持與你上述歷史發言一致之立場。"
                        f"特別注意：若歷史發布中包含最新的官方方針宣告，該最新方針具備最高權威，後續一切言行必須全力貫徹，絕不可退回舊立場或發表自相矛盾之言論！\n\n"
                    )
                    oasis.social_agent.agent.agent_log.info(f"Agent {self.social_agent_id} successfully loaded {len(past_posts)} past posts into Self-Action Memory")
        except Exception as e:
            oasis.social_agent.agent.agent_log.warning(f"Failed to load Self-Action Memory for Agent {self.social_agent_id}: {e}")

        env_prompt = await self.env.to_text_prompt()
        prompt = (
            f"Please perform social media actions after observing the "
            f"platform environments. Notice that don't limit your "
            f"actions for example to just like the posts.\n"
            f"{self_memory_prompt}"
            f"Here is your social media environment: {env_prompt}\n\n"
            f"IMPORTANT: You MUST choose ONE action from the tools below and output your choice strictly in JSON format.\n"
            f"Do not output any markdown code blocks or explanations, just raw JSON.\n"
            f"Available tools schema:\n{json.dumps(tools_schema, ensure_ascii=False, indent=2)}\n\n"
            f"Your output MUST be a JSON object with this exact structure:\n"
            f"{{\n"
            f'  "action_name": "the name of the tool to call",\n'
            f'  "args": {{ ...arguments for the tool... }}\n'
            f"}}\n"
        )
        
        user_msg = BaseMessage.make_user_message(role_name="User", content=prompt)
        
        try:
            oasis.social_agent.agent.agent_log.info(f"Agent {self.social_agent_id} observing environment (Bypassing ToolCall with JSON Prompt): {env_prompt}")
            
            # Remove tools to prevent vLLM error
            original_tools_config = None
            original_max_tokens = None
            original_temp = None
            
            if hasattr(self, 'model_backend') and hasattr(self.model_backend, 'model_config_dict'):
                original_tools_config = self.model_backend.model_config_dict.get("tools")
                original_max_tokens = self.model_backend.model_config_dict.get("max_tokens")
                original_temp = self.model_backend.model_config_dict.get("temperature")
                
                self.model_backend.model_config_dict.pop("tools", None)
                self.model_backend.model_config_dict.pop("tool_choice", None)
                self.model_backend.model_config_dict["max_tokens"] = 800
                self.model_backend.model_config_dict["temperature"] = 0.5
                
            original_agent_tools = getattr(self, 'tools', None)
            original_internal_tools = getattr(self, '_internal_tools', None)
            original_external_tool_schemas = getattr(self, '_external_tool_schemas', None)
            
            self.tools = None
            if hasattr(self, '_internal_tools'):
                self._internal_tools = {}
            if hasattr(self, '_external_tool_schemas'):
                self._external_tool_schemas = {}
            
            response = await self.astep(user_msg)
            
            # Restore tools just in case
            self.tools = original_agent_tools
            if original_internal_tools is not None and hasattr(self, '_internal_tools'):
                self._internal_tools = original_internal_tools
            if original_external_tool_schemas is not None and hasattr(self, '_external_tool_schemas'):
                self._external_tool_schemas = original_external_tool_schemas
                
            if original_tools_config and hasattr(self, 'model_backend'):
                self.model_backend.model_config_dict["tools"] = original_tools_config
                if original_max_tokens is not None:
                    self.model_backend.model_config_dict["max_tokens"] = original_max_tokens
                else:
                    self.model_backend.model_config_dict.pop("max_tokens", None)
                    
                if original_temp is not None:
                    self.model_backend.model_config_dict["temperature"] = original_temp
                else:
                    self.model_backend.model_config_dict.pop("temperature", None)
                
            content = response.msg.content
            
            # Parse JSON
            match = re.search(r'\{.*\}', content, re.DOTALL)
            tool_calls_mock = []
            if match:
                try:
                    action_data = json.loads(match.group(0))
                    class MockToolCall:
                        def __init__(self, name, args):
                            self.tool_name = name
                            self.args = args
                            self.result = "Success"
                            
                    action_name = action_data.get("action_name", "do_nothing")
                    args = action_data.get("args", {})
                    
                    # Manually execute the tool since we bypassed camel-ai's execution
                    if action_name in original_internal_tools:
                        tool = original_internal_tools[action_name]
                        try:
                            import inspect
                            if hasattr(tool, 'func') and hasattr(tool.func, 'async_call'):
                                await tool.func.async_call(**args)
                            elif hasattr(tool, 'async_call') and callable(tool.async_call):
                                await tool.async_call(**args)
                            elif hasattr(tool, 'func') and inspect.iscoroutinefunction(tool.func):
                                await tool.func(**args)
                            else:
                                if hasattr(tool, 'func'):
                                    tool.func(**args)
                                else:
                                    tool(**args)
                            oasis.social_agent.agent.agent_log.info(f"Agent {self.social_agent_id} successfully executed {action_name} to database")
                        except Exception as e:
                            oasis.social_agent.agent.agent_log.error(f"Agent {self.social_agent_id} failed to execute {action_name}: {e}")
                    
                    tool_calls_mock.append(MockToolCall(action_name, args))
                except Exception as e:
                    oasis.social_agent.agent.agent_log.error(f"Agent {self.social_agent_id} JSON Parse Error: {e} in {content}")
            else:
                oasis.social_agent.agent.agent_log.warning(f"Agent {self.social_agent_id} returned no JSON match in {content}")
                
            response.info = getattr(response, 'info', {}) or {}
            response.info['tool_calls'] = tool_calls_mock
            
            for tool_call in response.info.get('tool_calls', []):
                action_name = tool_call.tool_name
                args = tool_call.args
                oasis.social_agent.agent.agent_log.info(f"Agent {self.social_agent_id} performed action: {action_name} with args: {args}")
                if action_name not in oasis.social_agent.agent.ALL_SOCIAL_ACTIONS:
                    oasis.social_agent.agent.agent_log.info(f"Agent {self.social_agent_id} get the result: {tool_call.result}")
            
            return response
            
        except Exception as e:
            oasis.social_agent.agent.agent_log.error(f"Agent {self.social_agent_id} error: {e}")
            return e

    oasis.social_agent.agent.SocialAgent.perform_action_by_llm = patched_perform_action_by_llm
    logger.info("Successfully monkey-patched SocialAgent.perform_action_by_llm to use JSON Prompt instead of Tool Calling.")
except Exception as e:
    logger.warning(f"Failed to monkey patch SocialAgent: {e}")
