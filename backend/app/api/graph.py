"""
圖譜相關API路由
採用專案上下文機制，服務端持久化狀態
"""

from app.services import graph_builder
import os
import traceback
import threading
from flask import request, jsonify

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..utils.locale import t, get_locale, set_locale
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus

# 獲取日誌器
logger = get_logger('mirofish.api')


def allowed_file(filename: str) -> bool:
    """檢查副檔名是否允許"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== 專案管理介面 ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    獲取專案詳情
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    列出所有專案
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(limit=limit)
    
    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    刪除專案
    """
    success = ProjectManager.delete_project(project_id)
    
    if not success:
        return jsonify({
            "success": False,
            "error": t('api.projectDeleteFailed', id=project_id)
        }), 404

    return jsonify({
        "success": True,
        "message": t('api.projectDeleted', id=project_id)
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    重置專案狀態（用於重新構建圖譜）
    """
    project = ProjectManager.get_project(project_id)
    
    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    # 重置到本體已生成狀態
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED
    
    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)
    
    return jsonify({
        "success": True,
        "message": t('api.projectReset', id=project_id),
        "data": project.to_dict()
    })


# ============== 介面1：上傳檔案並生成本體 ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    介面1：上傳檔案，分析生成本體定義
    
    請求方式：multipart/form-data
    
    引數：
        files: 上傳的檔案（PDF/MD/TXT），可多個
        simulation_requirement: 模擬需求描述（必填）
        project_name: 專案名稱（可選）
        additional_context: 額外說明（可選）
        
    返回：
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== 開始生成本體定義 ===")
        
        # 獲取引數
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')
        
        logger.debug(f"專案名稱: {project_name}")
        logger.debug(f"模擬需求: {simulation_requirement[:100]}...")
        
        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": t('api.requireSimulationRequirement')
            }), 400
        
        # 獲取上傳的檔案
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": t('api.requireFileUpload')
            }), 400
        
        # 建立專案
        project = ProjectManager.create_project(name=project_name)
        project.simulation_requirement = simulation_requirement
        logger.info(f"建立專案: {project.project_id}")
        
        # 儲存檔案並提取文字
        document_texts = []
        all_text = ""
        
        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # 儲存檔案到專案目錄
                file_info = ProjectManager.save_file_to_project(
                    project.project_id, 
                    file, 
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })
                
                # 提取文字
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"
        
        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": t('api.noDocProcessed')
            }), 400
        
        # 儲存提取的文字
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"文字提取完成，共 {len(all_text)} 字元")
        
        # 生成本體
        logger.info("呼叫 LLM 生成本體定義... (這可能需要 10-15 分鐘，請耐心等待)")
        generator = OntologyGenerator()
        
        try:
            ontology = generator.generate(
                document_texts=document_texts,
                simulation_requirement=simulation_requirement,
                additional_context=additional_context if additional_context else None
            )
            logger.debug("LLM 回傳原始資料成功，開始解析內容...")
        except Exception as llm_err:
            logger.error(f"LLM 生成過程發生錯誤: {str(llm_err)}")
            raise llm_err
        
        # 儲存本體到專案
        try:
            entity_count = len(ontology.get("entity_types", []))
            edge_count = len(ontology.get("edge_types", []))
            logger.info(f"本體解析成功: {entity_count} 個實體型別, {edge_count} 個關係型別")
            
            project.ontology = {
                "entity_types": ontology.get("entity_types", []),
                "edge_types": ontology.get("edge_types", [])
            }
            project.analysis_summary = ontology.get("analysis_summary", "")
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            
            logger.debug(f"正在儲存專案資料到磁碟: {project.project_id}")
            ProjectManager.save_project(project)
            logger.info(f"=== 本體生成並儲存完成 === 專案ID: {project.project_id}")
        except Exception as save_err:
            logger.error(f"儲存專案資料時發生錯誤: {str(save_err)}")
            raise save_err
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 介面2：構建圖譜 ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    介面2：根據project_id構建圖譜
    
    請求（JSON）：
        {
            "project_id": "proj_xxxx",  // 必填，來自介面1
            "graph_name": "圖譜名稱",    // 可選
            "chunk_size": 500,          // 可選，預設500
            "chunk_overlap": 50         // 可選，預設50
        }
        
    返回：
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "圖譜構建任務已啟動"
            }
        }
    """
    try:
        logger.info("=== 開始構建圖譜 ===")
        
        # 檢查配置
        errors = []
        if not Config.ZEP_API_KEY:
            errors.append(t('api.zepApiKeyMissing'))
        if errors:
            logger.error(f"配置錯誤: {errors}")
            return jsonify({
                "success": False,
                "error": t('api.configError', details="; ".join(errors))
            }), 500
        
        # 解析請求
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"請求引數: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": t('api.requireProjectId')
            }), 400
        
        # 獲取專案
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=project_id)
            }), 404

        # 檢查專案狀態
        force = data.get('force', False)  # 強制重新構建
        
        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": t('api.ontologyNotGenerated')
            }), 400
        
        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": t('api.graphBuilding'),
                "task_id": project.graph_build_task_id
            }), 400
        
        # 如果強制重建，重置狀態
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None
        
        # 獲取配置
        graph_name = data.get('graph_name', project.name or 'MiroFish Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)
        
        # 更新專案配置
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap
        
        # 獲取提取的文字
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": t('api.textNotFound')
            }), 400
        
        # 獲取本體
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": t('api.ontologyNotFound')
            }), 400
        
        # 建立非同步任務
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"構建圖譜: {graph_name}")
        logger.info(f"建立圖譜構建任務: task_id={task_id}, project_id={project_id}")
        
        # 更新專案狀態
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)
        
        # Capture locale before spawning background thread
        current_locale = get_locale()

        # 啟動後臺任務
        def build_task():
            set_locale(current_locale)
            build_logger = get_logger('mirofish.build')
            try:
                build_logger.info(f"[{task_id}] 開始構建圖譜...")
                task_manager.update_task(
                    task_id, 
                    status=TaskStatus.PROCESSING,
                    message=t('progress.initGraphService')
                )
                
                # 建立圖譜構建服務
                builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
                
                # =====================================================================
                # 建立圖譜與設定本體 (不論哪種模式，這都是必須的)
                # =====================================================================
                task_manager.update_task(
                    task_id,
                    message=t('progress.creatingZepGraph'),
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name)
                
                # 更新專案的graph_id
                project.graph_id = graph_id
                ProjectManager.save_project(project)
                
                # 設定本體
                task_manager.update_task(
                    task_id,
                    message=t('progress.settingOntology'),
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)
                
                # 初始化分塊數（供任務結束結果讀取，固定連線模式下為0）
                total_chunks = 0
                
                # =====================================================================
                # [新增功能] 檢查是否為強制固定連線模式 [FIXED_GRAPH]
                # =====================================================================
                fixed_idx = text.find("[FIXED_GRAPH]")
                sim_req = getattr(project, 'simulation_requirement', '') or ""
                sim_idx = sim_req.find("[FIXED_GRAPH]")
                
                if fixed_idx != -1 or sim_idx != -1:
                    build_logger.info(f"[{task_id}] 偵測到 [FIXED_GRAPH]，啟動強制寫入模式...")
                    task_manager.update_task(
                        task_id,
                        message="啟動 [FIXED_GRAPH] 強制寫入模式...",
                        progress=20
                    )
                    import time
                    
                    # 從 [FIXED_GRAPH] 之後開始解析 (優先使用上傳檔案，其次使用模擬需求)
                    fixed_text = text[fixed_idx:] if fixed_idx != -1 else sim_req[sim_idx:]
                    lines = fixed_text.strip().split('\n')[1:] # 跳過第一行標籤
                    valid_edges = []
                    for line in lines:
                        line = line.strip()
                        if not line or line.startswith('#'): continue
                        parts = [p.strip() for p in line.split(',')]
                        if len(parts) >= 3:
                            valid_edges.append((parts[0], parts[1], parts[2]))
                    
                    total_edges = len(valid_edges)
                    
                    # 直接寫入 Zep 資料庫
                    for i, (source, rel, target) in enumerate(valid_edges):
                        build_logger.info(f"[{task_id}] 強制寫入連線: {source} -[{rel}]-> {target}")
                        task_manager.update_task(
                            task_id,
                            message=f"強制寫入連線: {source} -[{rel}]-> {target}",
                            progress=20 + int((i / total_edges) * 60) if total_edges > 0 else 80
                        )
                        
                        try:
                            builder.client.graph.add_fact_triple(
                                graph_id=graph_id,
                                fact=f"{source} {rel} {target}",
                                fact_name=rel.upper().replace(' ', '_'),
                                source_node_name=source,
                                target_node_name=target
                            )
                            # 為確保 Zep 處理不過載，稍微延遲
                            time.sleep(0.5)
                        except Exception as e:
                            build_logger.error(f"Failed to add edge {source}-{rel}-{target}: {e}")
                    
                    build_logger.info(f"[{task_id}] 固定連線寫入完成，共 {total_edges} 條線。")
                    task_manager.update_task(
                        task_id,
                        message="固定連線寫入完成",
                        progress=90
                    )
                    
                    # 等待 Zep 索引完成 (輪詢直到邊的數量等於寫入的數量，最長等待 30 秒)
                    build_logger.info(f"[{task_id}] 等待 Zep 索引三元組...")
                    start_wait = time.time()
                    while time.time() - start_wait < 30:
                        try:
                            temp_data = builder.get_graph_data(graph_id)
                            current_edges = temp_data.get("edge_count", 0)
                            build_logger.info(f"[{task_id}] 檢查 Zep 索引進度: {current_edges}/{total_edges} 條邊")
                            if current_edges >= total_edges:
                                build_logger.info(f"[{task_id}] Zep 索引完成，已找到全部 {total_edges} 條邊。")
                                break
                        except Exception as e:
                            build_logger.warning(f"Error checking edge count: {e}")
                        time.sleep(2)
                    
                else:
                    # =====================================================================
                    # [原本舊的程式碼] 一般 LLM 萃取模式
                    # 註解說明：這裡的程式碼完全沒有被刪除！
                    # 只要您在前端沒有輸入 [FIXED_GRAPH]，系統就會自動跑回這段原本的邏輯。
                    # 因此未來您不需要再改回任何程式碼，新舊功能是共存的！
                    # =====================================================================
                    
                    # 分塊
                    task_manager.update_task(
                        task_id,
                        message=t('progress.textChunking'),
                        progress=5
                    )
                    chunks = TextProcessor.split_text(
                        text, 
                        chunk_size=chunk_size, 
                        overlap=chunk_overlap
                    )
                    total_chunks = len(chunks)

                #      # 建立圖譜(舊的程式碼，是為了要能夠直接強制讀取實體之間的關聯)
                # task_manager.update_task(
                #     task_id,
                #     message=t('progress.creatingZepGraph'),
                #     progress=10
                # )
                # graph_id = builder.create_graph(name=graph_name)
                
                # # 更新專案的graph_id
                # project.graph_id = graph_id
                # ProjectManager.save_project(project)
                
                # # 設定本體
                # task_manager.update_task(
                #     task_id,
                #     message=t('progress.settingOntology'),
                #     progress=15
                # )
                # builder.set_ontology(graph_id, ontology)
                    
                    # 新增文字（progress_callback 簽名是 (msg, progress_ratio)）
                    def add_progress_callback(msg, progress_ratio):
                        progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                        task_manager.update_task(
                            task_id,
                            message=msg,
                            progress=progress
                        )
                    
                    task_manager.update_task(
                        task_id,
                        message=t('progress.addingChunks', count=total_chunks),
                        progress=15
                    )
                    
                    episode_uuids = builder.add_text_batches(
                        graph_id, 
                        chunks,
                        batch_size=3,
                        progress_callback=add_progress_callback
                    )
                    
                    # 等待Zep處理完成（查詢每個episode的processed狀態）
                    task_manager.update_task(
                        task_id,
                        message=t('progress.waitingZepProcess'),
                        progress=55
                    )
                    
                    def wait_progress_callback(msg, progress_ratio):
                        progress = 55 + int(progress_ratio * 35)  # 55% - 90%
                        task_manager.update_task(
                            task_id,
                            message=msg,
                            progress=progress
                        )
                    
                    builder._wait_for_episodes(episode_uuids, wait_progress_callback)
                
                # 獲取圖譜資料
                task_manager.update_task(
                    task_id,
                    message=t('progress.fetchingGraphData'),
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)
                
                # 更新專案狀態
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)
                
                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] 圖譜構建完成: graph_id={graph_id}, 節點={node_count}, 邊={edge_count}")
                
                # 完成
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message=t('progress.graphBuildComplete'),
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )
                
            except Exception as e:
                # 更新專案狀態為失敗
                build_logger.error(f"[{task_id}] 圖譜構建失敗: {str(e)}")
                build_logger.debug(traceback.format_exc())
                
                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)
                
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=t('progress.buildFailed', error=str(e)),
                    error=traceback.format_exc()
                )
        
        # 啟動後臺執行緒
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": t('api.graphBuildStarted', taskId=task_id)
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== 任務查詢介面 ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    查詢任務狀態
    """
    task = TaskManager().get_task(task_id)
    
    if not task:
        return jsonify({
            "success": False,
            "error": t('api.taskNotFound', id=task_id)
        }), 404
    
    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
def list_tasks():
    """
    列出所有任務
    """
    tasks = TaskManager().list_tasks()
    
    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== 圖譜資料介面 ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    獲取圖譜資料（節點和邊）
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": t('api.zepApiKeyMissing')
            }), 500
        
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        graph_data = builder.get_graph_data(graph_id)
        
        return jsonify({
            "success": True,
            "data": graph_data
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    刪除Zep圖譜
    """
    try:
        if not Config.ZEP_API_KEY:
            return jsonify({
                "success": False,
                "error": t('api.zepApiKeyMissing')
            }), 500
        
        builder = GraphBuilderService(api_key=Config.ZEP_API_KEY)
        builder.delete_graph(graph_id)
        
        return jsonify({
            "success": True,
            "message": t('api.graphDeleted', id=graph_id)
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
