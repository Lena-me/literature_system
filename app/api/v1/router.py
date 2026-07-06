from fastapi import APIRouter
from app.modules.auth.router import router as auth_router
from app.modules.users.router import router as users_router
from app.modules.papers.router import router as papers_router
from app.modules.qa.router import router as qa_router
from app.modules.reports.router import router as reports_router
from app.modules.comparisons.router import router as comparisons_router
from app.modules.knowledge_graphs.router import router as kg_router
from app.modules.experiments.router import router as exp_router
from app.modules.learning_records.router import router as learning_router
from app.modules.paper_notes.router import router as paper_notes_router
from app.modules.formula.router import router as formula_router
from app.modules.admin.router import router as admin_router
from app.modules.model_configs.router import router as model_router
from app.modules.tasks.router import router as tasks_router
from app.modules.audit_logs.router import router as audit_router
from app.modules.vector_store.router import router as vector_router
from app.modules.system.router import router as system_router
from app.modules.analytics.router import router as analytics_router

api_router = APIRouter()
router_list = [
    auth_router, users_router, papers_router, qa_router, reports_router, comparisons_router, kg_router,exp_router,
    learning_router, paper_notes_router, formula_router, admin_router, model_router, tasks_router, audit_router, vector_router,system_router,
    analytics_router
]
for router in router_list:
    api_router.include_router(router)

