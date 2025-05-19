from .assistant_agent import ConfigurableAssistantAgent, get_llm_config_from_app
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

class APIDesignGeneratorAgent(ConfigurableAssistantAgent):
    """
    API設計書の生成を担当するAgent。
    CodebaseAnalyzerAgentからの分析結果の特定API部分を受け取り、そのAPIの仕様を生成します。
    """
    DEFAULT_SYSTEM_MESSAGE = "あなたはプロフェッショナルなAPI設計書作成アシスタントです。提供された情報を元に、詳細なAPI仕様書を日本語で作成してください。" # フォールバック用

    def __init__(self, app_config: Dict[str, Any], **kwargs):
        """
        コンストラクタ。

        Args:
            app_config (Dict[str, Any]): アプリケーション設定。
            **kwargs: ConfigurableAssistantAgentに渡されるその他の引数。
        """
        agent_name = "APIDesignGenerator"
        llm_config = get_llm_config_from_app(app_config)
        
        prompts_config = app_config.get('prompts', {})
        system_message = prompts_config.get('api_design_generator', self.DEFAULT_SYSTEM_MESSAGE)
        
        super().__init__(
            name=agent_name,
            llm_config=llm_config,
            system_message=system_message,
            **kwargs
        )

    def generate_api_document_prompt(self, single_api_analysis: str, full_analysis_report: Optional[str] = None) -> str:
        """
        単一のAPIに関する設計書を生成させるためのLLMへの指示メッセージを作成します。
        このメッセージは、UserProxyAgentからこのAgent (AssistantAgent) に送信され、
        LLMがAPI設計書を生成する際の基礎となります。

        Args:
            single_api_analysis (str): CodebaseAnalyzerAgentによって抽出された、
                                       単一のAPIエンドポイントに関する分析情報ブロック。
            full_analysis_report (Optional[str]): CodebaseAnalyzerAgentによって生成された
                                                  完全なコード分析レポート。追加コンテキストとして利用可能。

        Returns:
            str: LLMへのAPI設計書生成指示を含むメッセージ文字列。
        """
        
        # システムプロンプト (api_design_generator) には既に「各APIエンドポイントについて」詳細な指示と
        # Markdownテンプレートが含まれています。
        # そのため、ここではユーザーメッセージとして、分析対象となる単一のAPI情報を提供します。
        # full_analysis_report もコンテキストとして含めることで、API間の関連性や
        # DTOの詳細などをLLMが参照できる可能性を高めます（トークン数に注意）。

        prompt_parts = []
        prompt_parts.append("以下のAPI分析情報に基づいて、このAPIに関する詳細な設計書を、システムプロンプトの指示に従って作成してください。")
        prompt_parts.append("\n--- 対象API分析情報 ---")
        prompt_parts.append(f"```text\n{single_api_analysis}\n```")

        if full_analysis_report:
            prompt_parts.append("\n--- 全体コード分析レポート (参考コンテキスト) ---")
            # トークン数を考慮し、全体レポートはサマリーや必要な部分に絞ることも検討できますが、
            # まずはそのまま渡してみます。
            # CodebaseAnalyzerAgentの出力の "== APIエンドポイント分析結果 ==" 以外の部分
            # (DBエンティティやその他コンポーネント) が特に有用かもしれません。
            # ここでは簡単のため、APIリスト以外の部分を抽出する処理は省略し、
            # 必要であれば Agent のプロンプト側で「このAPI情報に基づいて」と明記することで、
            # LLMが single_api_analysis に集中するように促します。
            # もしくは、`app.py` 側で `full_analysis_report` からAPIリスト部分を除去して渡すことも考えられます。
            # 今回は、`single_api_analysis` に集中するよう指示し、`full_analysis_report` は補足とします。
            prompt_parts.append("以下の全体分析レポートは、必要に応じて参照してください（特にDTOの定義や他のコンポーネントとの関連など）。ただし、設計書の主対象は上記の「対象API分析情報」です。")
            prompt_parts.append(f"```text\n{full_analysis_report}\n```")
        
        prompt_parts.append("\n指示に従い、Mermaid図を含めたこのAPI専用の詳細な設計書を日本語で生成してください。")
        
        return "\n\n".join(prompt_parts) 