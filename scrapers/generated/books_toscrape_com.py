import asyncio
from bs4 import BeautifulSoup
from httpx import AsyncClient

class Scraper:
    target_domain = "books.toscrape.com"

    def __init__(self):
        self.base_url = "http://books.toscrape.com/catalogue/"
    
    async def scrape_products(self, query: str) -> list[dict]:
        client = AsyncClient()
        response = await client.get(f"{self.base_url}index.html")
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            products = []
            
            for book in soup.select('.product_pod'):
                title = book.h3.a['title']
                url = self.base_url + book.h3.a['href'][1:]
                price = book.select_one('.price_color').text
                currency = "£"
                
                products.append({
                    'title': title,
                    'price': price,
                    'currency': currency,
                    'product_url': url,
                    'store_name': 'Books to Scrape'
                })
            
            await client.aclose()
            return products
        else:
            print("Failed to fetch the page")
            await client.aclose()
            return []