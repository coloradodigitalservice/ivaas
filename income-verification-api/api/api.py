from django.http import HttpRequest
from ninja import NinjaAPI

api = NinjaAPI()


@api.get("/hello")
async def hello(request: HttpRequest) -> dict[str, str]:
    return {"message": "Hello, world!"}
