from .assistant_agent import ConfigurableAssistantAgent, get_llm_config_from_app
from typing import Dict, Any, Optional, List
from pathlib import Path # Pathオブジェクトを扱うために追加
import logging # ログ出力用

logger = logging.getLogger(__name__)

class CodebaseAnalyzerAgent(ConfigurableAssistantAgent):
    """
    Javaコードベースの分析を担当するAgent。
    """
    DEFAULT_SYSTEM_MESSAGE = "あなたはJavaコードベースを分析する専門家です。提供された情報を元に、コードの構造や主要な機能を特定してください。"
    MAX_FILES_TO_ANALYZE = 5  # 一度に分析するJavaファイルの最大数
    MAX_CHARS_PER_FILE = 4000 # 各ファイルから読み込む最大文字数 (トークン数に注意)

    def __init__(self, app_config: Dict[str, Any], **kwargs):
        """
        コンストラクタ。

        Args:
            app_config (Dict[str, Any]): アプリケーション設定。
            **kwargs: ConfigurableAssistantAgentに渡されるその他の引数。
        """
        agent_name = "JavaCodeAnalyzer"
        llm_config = get_llm_config_from_app(app_config)
        
        prompts_config = app_config.get('prompts', {})
        system_message = prompts_config.get('codebase_analyzer', self.DEFAULT_SYSTEM_MESSAGE)
        
        super().__init__(
            name=agent_name,
            llm_config=llm_config,
            system_message=system_message,
            **kwargs
        )

    def analyze_codebase(self, codebase_path: str, java_files: List[Path], project_structure: str) -> str:
        """
        コードベースの分析を実行するための詳細なプロンプトメッセージを生成します。
        このメッセージはUserProxyAgentからこのAgent (AssistantAgent) に送信され、LLMによる分析の基礎となります。

        Args:
            codebase_path (str): 分析対象のコードベースのパス。
            java_files (List[Path]): 検出されたJavaファイルのPathオブジェクトのリスト。
            project_structure (str): プロジェクトのディレクトリ構造を表す文字列。

        Returns:
            str: LLMへの分析指示を含む詳細なメッセージ文字列。
        """
        num_java_files_total = len(java_files)
        
        # LLMに渡すメッセージの構築開始 (全体を三重引用符で囲む)
        analysis_prompt_message = f"""Javaコードベースの分析リクエスト：

プロジェクトパス: {codebase_path}
検出されたJavaファイル総数: {num_java_files_total}

プロジェクト構造の概要:
```text
{project_structure[:1000]}...
```

主要なJavaファイルの分析:
分析対象として、以下のJavaファイルの内容（一部）を提供します。
これらの情報とあなたの知識に基づき、プロジェクトの主要なAPIエンドポイント、データベースエンティティ、
およびその他の重要なコンポーネントを特定し、構造化された形式で報告してください。
特にSpring BootのRestControllerアノテーションやJPAのEntityアノテーションに注目してください。
出力は、後続の設計書作成Agentが利用しやすいように、明確にセクション分けしてください。
例:
APIエンドポイント:
- GET /api/users: ユーザー一覧取得
- POST /api/users: 新規ユーザー作成
データベースエンティティ:
- User: id, name, email
- Order: id, userId, amount

"""

        files_to_include_in_prompt = java_files[:self.MAX_FILES_TO_ANALYZE]
        # この部分も、文字列の追加なので += を使うが、追加する文字列自体がf-string
        analysis_prompt_message += f"分析対象のファイル ({len(files_to_include_in_prompt)}件):\n\n"

        for i, file_path_obj in enumerate(files_to_include_in_prompt):
            try:
                relative_file_path = file_path_obj.relative_to(Path(codebase_path))
                # ファイルヘッダー部分 (f-string)
                analysis_prompt_message += f"--- ファイル {i+1}: {relative_file_path} ---\n"
                with open(file_path_obj, 'r', encoding='utf-8') as f:
                    content = f.read(self.MAX_CHARS_PER_FILE)
                    # コードブロック部分 (ここが重要、三重引用符のf-stringにする)
                    analysis_prompt_message += f"""```java
{content}
```
"""
                if len(content) == self.MAX_CHARS_PER_FILE:
                    analysis_prompt_message += "... (ファイル内容が長いため一部省略)\n"
                analysis_prompt_message += "\n" # 各ファイル間の追加の改行
            except Exception as e:
                logger.error(f"ファイル読み込みエラー ({file_path_obj}): {e}")
                analysis_prompt_message += f"--- ファイル {i+1}: {file_path_obj} (読み込みエラー: {e}) ---\n\n"
        
        analysis_prompt_message += "以上の情報を元に、詳細な分析結果を生成してください。"

        return analysis_prompt_message 