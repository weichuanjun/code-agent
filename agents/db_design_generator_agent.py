from .assistant_agent import ConfigurableAssistantAgent, get_llm_config_from_app
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class DBDesignGeneratorAgent(ConfigurableAssistantAgent):
    """
    データベース設計書の生成を担当するAgent。
    CodebaseAnalyzerAgentからの分析結果を受け取り、DBスキーマ情報やER図を生成します。
    """
    DEFAULT_SYSTEM_MESSAGE = "あなたは経験豊富なデータベース設計アシスタントです。提供された情報を元に、詳細なデータベース設計書を日本語で作成してください。" # フォールバック用

    def __init__(self, app_config: Dict[str, Any], **kwargs):
        """
        コンストラクタ。

        Args:
            app_config (Dict[str, Any]): アプリケーション設定。
            **kwargs: ConfigurableAssistantAgentに渡されるその他の引数。
        """
        agent_name = "DBDesignGenerator"
        llm_config = get_llm_config_from_app(app_config)
        
        prompts_config = app_config.get('prompts', {})
        system_message = prompts_config.get('db_design_generator', self.DEFAULT_SYSTEM_MESSAGE)
        
        super().__init__(
            name=agent_name,
            llm_config=llm_config,
            system_message=system_message,
            **kwargs
        )

    def generate_db_document_prompt(self, analysis_report: str) -> str:
        """
        データベース設計書を生成させるためのLLMへの指示メッセージを作成します。
        このメッセージは、UserProxyAgentからこのAgent (AssistantAgent) に送信され、
        LLMがデータベース設計書を生成する際の基礎となります。

        Args:
            analysis_report (str): CodebaseAnalyzerAgentによって生成されたコード分析レポート。
                                   このレポートには、データベースエンティティに関する情報が含まれていることを期待します。

        Returns:
            str: LLMへのデータベース設計書生成指示を含むメッセージ文字列。
        """
        
        prompt = f"""提供された以下のコード分析レポートに基づいて、データベース設計書を作成してください。

分析レポート:
```text
{analysis_report}
```

指示に従い、ER図 (Mermaid形式) や状態遷移図 (Mermaid形式) を含めた詳細なデータベース設計書を日本語で生成してください。
"""
        return prompt 