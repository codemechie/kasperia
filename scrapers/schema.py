from pydantic import BaseModel, HttpUrl, Field
from typing import Optional
from datetime import datetime

class ProductDeal(BaseModel):
    title: str = Field(..., min_length=2)
    price: float = Field(..., gt=0.0)
    currency: str = Field(default="USD", max_length=3)
    product_url: HttpUrl
    image_url: Optional[HttpUrl] = None
    store_name: str
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
