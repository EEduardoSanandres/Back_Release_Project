from .pdf_service import PdfService
from .story_service import StoryService
from .graph_service import GraphService
from .release_service import ReleaseService

def pdf_service()    -> PdfService:    return PdfService()
def story_service()  -> StoryService:  return StoryService()
def graph_service()  -> GraphService:  return GraphService()
def release_service()-> ReleaseService:return ReleaseService()
