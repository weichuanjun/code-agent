# このファイルは file_utils モジュールです。
# ファイル操作やディレクトリ関連のユーティリティ関数をここに配置します。

import os
from pathlib import Path
import re # re モジュールをインポート
from typing import Optional, Tuple # 追加

def get_java_files(directory_path: str):
    """
    指定されたディレクトリ内のすべての .java ファイルのリストを再帰的に取得します。

    Args:
        directory_path (str): 検索対象のディレクトリパス。

    Returns:
        list[Path]: .java ファイルのPathオブジェクトのリスト。
    """
    java_files = []
    root_path = Path(directory_path)
    if not root_path.is_dir():
        return [] # ディレクトリが存在しない場合は空のリストを返す

    for file_path in root_path.rglob('*.java'):
        java_files.append(file_path)
    return java_files

def get_project_structure_text(root_dir_str: str, max_depth=5, indent_char='    ', max_items_per_dir=20, include_files: bool = True) -> str:
    """
    指定されたディレクトリの構造をテキストベースのツリー形式で取得します。
    表示する深さやアイテム数を制限できます。

    Args:
        root_dir_str (str): ルートディレクトリのパス。
        max_depth (int): 表示する最大の深さ。
        indent_char (str): インデントに使用する文字。
        max_items_per_dir (int): 各ディレクトリで表示する最大のアイテム数。
        include_files (bool): ファイルも表示に含めるかどうか。デフォルトはTrue。

    Returns:
        str: ディレクトリ構造を表す文字列。
    """
    root_dir = Path(root_dir_str)
    if not root_dir.is_dir():
        return "指定されたパスはディレクトリではありません。"

    tree_lines = [f"📁 {root_dir.name}/"]

    def _build_tree(current_dir: Path, current_depth: int, prefix: str):
        if current_depth >= max_depth:
            tree_lines.append(f"{prefix}└── ... (深さ制限に到達)")
            return

        try:
            # include_files が False の場合はディレクトリのみをリストアップ
            if include_files:
                entries = sorted(list(current_dir.iterdir()), key=lambda e: (e.is_file(), e.name.lower()))
            else:
                entries = sorted([e for e in current_dir.iterdir() if e.is_dir()], key=lambda e: e.name.lower())
                # ディレクトリのみの場合、ファイルも存在する可能性を示すために、ファイルがあるかどうかのチェックを追加しても良い
                if not entries and any(e.is_file() for e in current_dir.iterdir()): # ディレクトリがなくファイルはある場合
                     if current_depth < max_depth -1 : #深すぎない場合のみ表示
                        tree_lines.append(f"{prefix}{indent_char}...(ファイルのみ存在)")


        except PermissionError:
            tree_lines.append(f"{prefix}└── 🔒 (アクセス権がありません)")
            return
        except Exception as e:
            tree_lines.append(f"{prefix}└── ⚠️ (読み取りエラー: {e})")
            return
            
        display_count = 0
        # フィルタリングされたエントリの数を正しく使う
        effective_entry_count = len(entries)

        for i, entry in enumerate(entries):
            if display_count >= max_items_per_dir:
                tree_lines.append(f"{prefix}└── ... (他 {effective_entry_count - display_count} アイテム)")
                break
            
            # コネクタの決定ロジックを修正
            is_last_entry_to_display = (i == effective_entry_count - 1) or (display_count == max_items_per_dir - 1)
            connector = "└── " if is_last_entry_to_display else "├── "
            
            if entry.is_dir():
                tree_lines.append(f"{prefix}{connector}📁 {entry.name}/")
                # インデントのprefixを修正
                new_prefix = prefix + (indent_char if connector == "├── " else "    ") 
                _build_tree(entry, current_depth + 1, new_prefix)
            elif include_files: # include_files が True の場合のみファイルを表示
                tree_lines.append(f"{prefix}{connector}📄 {entry.name}")
            display_count += 1

    _build_tree(root_dir, 0, "")
    return "\n".join(tree_lines) 

def sanitize_filename(filename: str) -> str:
    """
    ファイル名として安全でない可能性のある文字をアンダースコアに置換します。
    スペースもアンダースコアに置換します。
    """
    filename = re.sub(r'[\s/:*?"<>|]+', '_', filename)
    return filename

def save_markdown_to_file(content: str, directory: Path, filename: str) -> Tuple[bool, Optional[str]]:
    """
    指定されたディレクトリにMarkdownコンテンツをファイルとして保存します。
    ディレクトリが存在しない場合は作成します。

    Args:
        content (str): 保存するMarkdown文字列。
        directory (Path): 保存先のディレクトリ。
        filename (str): 保存するファイル名 (例: "my_document.md")。

    Returns:
        Tuple[bool, Optional[str]]: 保存に成功した場合は (True, None)、失敗した場合は (False, エラーメッセージ文字列)。
    """
    try:
        directory.mkdir(parents=True, exist_ok=True)
        file_path = directory / filename
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(content)
        return True, None
    except Exception as e:
        return False, str(e) 