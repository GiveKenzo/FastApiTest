from settings import *
from methods import *

from fastapi import FastAPI, Response, status, Depends, Query, File, UploadFile
from typing import Optional, List
from starlette.responses import FileResponse
from db_connect import engine, SessionLocal
import db_models 
from sqlalchemy.orm import Session
from fastapi import HTTPException


# DB
db_models.Base.metadata.create_all(engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
# End DB

app = FastAPI()

@app.get("/api/get", tags = ["Get files"], status_code=status.HTTP_200_OK)
async def root(
                #.*,
                response: Response,
                id: Optional[List[int]] = Query(None),
                name: Optional[List[str]] = Query(None),
                tag: Optional[List[str]] = Query(None),
                limit: Optional[int] = None,
                offset: Optional[int] = None,
                db: Session = Depends(get_db)
            ):

    # All recodrs by default
    query = db.query(db_models.Image).all()
    files_in_db = get_files_from_db_limit_offset(db, query, limit, offset)

    if id and not name and not tag:
        query = db.query(db_models.Image).filter(db_models.Image.file_id.in_(id)).all()
        files_in_db = get_files_from_db_limit_offset(db, query, limit, offset)

    elif id and name and not tag:
        query = db.query(db_models.Image).filter(db_models.Image.file_id.in_(id)) \
                                        .filter(db_models.Image.name.in_(name)) \
                                        .all()
        files_in_db = get_files_from_db_limit_offset(db, query, limit, offset)

    elif id and name and tag:
        query = db.query(db_models.Image).filter(db_models.Image.file_id.in_(id)) \
                                        .filter(db_models.Image.name.in_(name)) \
                                        .filter(db_models.Image.tag.in_(tag)) \
                                        .all()
        files_in_db = get_files_from_db_limit_offset(db, query, limit, offset)

    elif id and not name and tag:
        query = db.query(db_models.Image).filter(db_models.Image.file_id.in_(id)) \
                                        .filter(db_models.Image.tag.in_(tag)) \
                                        .all()
        files_in_db = get_files_from_db_limit_offset(db, query, limit, offset)

    elif not id and name and tag:
        query = db.query(db_models.Image).filter(db_models.Image.name.in_(name)) \
                                        .filter(db_models.Image.tag.in_(tag)) \
                                        .all()
        files_in_db = get_files_from_db_limit_offset(db, query, limit, offset)

    elif not id and not name and tag:
        query = db.query(db_models.Image).filter(db_models.Image.tag.in_(tag)).all()
        files_in_db = get_files_from_db_limit_offset(db, query, limit, offset)

    elif not id and name and not tag:
        query = db.query(db_models.Image).filter(db_models.Image.name.in_(name)).all()
        files_in_db = get_files_from_db_limit_offset(db, query, limit, offset)

    if len(files_in_db) == 0:
        response.status_code = status.HTTP_400_NOT_FOUND
        return {'message': 'No results = ('}

    response.status_code = status.HTTP_200_OK
    return files_in_db

@app.post("/api/upload", tags = ["Upload"], status_code = status.HTTP_200_OK)
async def upload_file(
                        response: Response,
                        file_id: int,
                        name: Optional[str] = None,
                        tag: Optional[str] = None,
                        file: UploadFile = File(...),
                        db: Session = Depends(get_db)
                    ):

    # Format new filename
    full_name = format_filename(file, file_id, name)
    
    # Save file
    await save_file_to_uploads(file, full_name)

    # Get file size
    file_size = get_file_size(full_name)

    # Get info from DB
    file_info_from_db = get_file_from_db(db, file_id)

    # Add to DB
    if not file_info_from_db:
        response.status_code = status.HTTP_201_CREATED
        return add_file_to_db(
                                db,
                                file_id = file_id,
                                full_name = full_name,
                                tag = tag,
                                file_size = file_size,
                                file = file
                            )

    # Update in DB
    if file_info_from_db:
        # Delete file from uploads
        delete_file_from_uploads(file_info_from_db.name)

        response.status_code = status.HTTP_201_CREATED
        return update_file_in_db(
                                db,
                                file_id = file_id,
                                full_name = full_name,
                                tag = tag,
                                file_size = file_size,
                                file = file
                            )

@app.get("/api/download", tags = ['Download'], status_code = status.HTTP_200_OK)
async def download_file(
                            response: Response,
                            file_id: int,
                            db: Session = Depends(get_db)
                        ):
    file_info_from_db = get_file_from_db(db, file_id)

    if file_info_from_db:
        file_resp = FileResponse(UPLOADED_FILES_PATH + file_info_from_db.name,
                                media_type=file_info_from_db.mime_type,
                                filename=file_info_from_db.name)
        response.status_code = status.HTTP_200_OK
        return file_resp
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return{'msg': 'File not found'}

@app.put("/api/update/{file_id}", tags=["Update"], status_code=status.HTTP_200_OK)
async def update_file(
                        file_id: int,
                        name: Optional[str] = None,
                        tag: Optional[str] = None,
                        file: UploadFile = File(None),
                        db: Session = Depends(get_db)
                    ):
    # Найти файл в базе данных по ID
    db_file = db.query(db_models.Image).filter(db_models.Image.file_id == file_id).first()
    if not db_file:
        raise HTTPException(status_code=404, detail="File not found")

    # Обновить информацию о файле, если предоставлено
    if name:
        db_file.name = name
    if tag:
        db_file.tag = tag

    # Обновить дату последнего изменения файла
    db_file.last_updated = datetime.utcnow()

    # Сохранить файл, если он был загружен
    if file:
        full_name = format_filename(file, file_id, name)
        await save_file_to_uploads(file, full_name)
        db_file.url = full_name  # Обновить URL файла в базе данных

    # Сохранить изменения в базе данных
    db.commit()
    db.refresh(db_file)

    return {"message": "File updated successfully"}

@app.delete("/api/delete", tags = ["Delete"])
async def download_file(
                            response: Response,
                            file_id: int,
                            db: Session = Depends(get_db)
                        ):
    file_info_from_db = get_file_from_db(db, file_id)

    if file_info_from_db:
        # Delete file from DB
        delete_file_from_db(db, file_info_from_db)

        # Delete file from uploads
        delete_file_from_uploads(file_info_from_db.name)
        
        response.status_code = status.HTTP_200_OK
        return {'msg': f'File {file_info_from_db.name}'}
    else:
        response.status_code = status.HTTP_404_NOT_FOUND
        return {'msg': f'File does not exist'}