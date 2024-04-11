# GiNo (Gitlab <-> Notion)

GiNo create a bridge between Gitlab and Notion.

## How to run

- Create `.env` file with following details.

```
NOTION_ACCESS_TOKEN = secret_ladidadadumdum 
GITLAB_URL = "https://gitlab.subcom.tech" 
GL_GROUP_TOKEN = t3xM-0000000000-21111
TASK_DATABASE_ID = 26e00000000000000000000000000000
```

```
GITLAB_URL = "https://gitlab.subcom.tech"
GL_GROUP_TOKEN = <gl_token>
TASK_DATABASE_ID = <notion_database_task>
NOTION_ACCESS_TOKEN = <notion_access_token>
```

- Run `gino run-once`
