from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Optional




app = FastAPI(title= "Book Store API 2", version= "1.1")


class Book(BaseModel):
    id: int
    title: str
    author: str
    customer_age: Optional[str] = None
    year: Optional[int] = None


new_book_db: List[Book] = [
    Book(
        id=0,
        title= "Nutuk",
        author= "M. K. Atatürk",
        customer_age= "15-20",
        year= 1932
    ),
    Book(
        id=1,
        title= "Ali Baba Çiftliği",
        author= "Ali Baba",
        year= 2005
    )
]


# --- CRUD İşlemleri ---
@app.get("/", tags=["Root"])
def root():
    "Başlangıç Sayfasını getirir"
    return {"message": "Welcome to the New Book Store API!"}

@app.get("/books", response_model=List[Book], tags=["Books"])
def get_newbooks():
    "Yeni kitapları getirir"
    return new_book_db

@app.get("/books/{book_id}", response_model=Book, tags=["Books"])
def get_book(book_id:int):
    "Belirli bir kitabı ID'ye göre getirir"
    for book in new_book_db:
        if book.id == book_id:
            return book
    raise HTTPException(status_code=404, detail="Kardeşim adam akıllı araştırma yapsana! Bu kütüphanede böyle bir kitap yok!")

@app.post("/books", response_model=Book, tags=["Books"])
def create_book(book_id:int):
    for book in new_book_db:
        if book.id == nook_id:
            



