set dotenv-load

export TF_VAR_telegram_bot_token := env_var_or_default("BOT_TOKEN", "")
export TF_VAR_aws_access_key := env_var_or_default("AWS_ACCESS_KEY_ID", "")
export TF_VAR_aws_secret_key := env_var_or_default("AWS_SECRET_ACCESS_KEY", "")

dist_dir := "dist"
stage_dir := ".build"
venv := ".venv"
pip := venv / "Scripts" / "pip.exe"
python := venv / "Scripts" / "python.exe"

install:
    {{pip}} install -r requirements-dev.txt

test:
    CONFIG_PATH=src {{python}} -m pytest tests/ -v

clean:
    rm -rf {{dist_dir}} {{stage_dir}}

package: clean
    mkdir -p {{dist_dir}}

    # --- notifier ---
    mkdir -p {{stage_dir}}/notifier
    cp src/notifier/handler.py {{stage_dir}}/notifier/
    cp src/config.json {{stage_dir}}/notifier/
    cp -r shared {{stage_dir}}/notifier/
    cd {{stage_dir}}/notifier && zip -r ../../{{dist_dir}}/notifier.zip .

    # --- reminder ---
    mkdir -p {{stage_dir}}/reminder
    cp src/reminder/handler.py {{stage_dir}}/reminder/
    cp src/config.json {{stage_dir}}/reminder/
    cp -r shared {{stage_dir}}/reminder/
    cd {{stage_dir}}/reminder && zip -r ../../{{dist_dir}}/reminder.zip .

    # --- webhook ---
    mkdir -p {{stage_dir}}/webhook
    cp src/webhook/handler.py {{stage_dir}}/webhook/
    cp -r shared {{stage_dir}}/webhook/
    cd {{stage_dir}}/webhook && zip -r ../../{{dist_dir}}/webhook.zip .

    rm -rf {{stage_dir}}
    echo "Packages built in {{dist_dir}}/"

deploy: package
    cd infra && terraform init && terraform apply

destroy:
    cd infra && terraform destroy

register-webhook: (_register-webhook `cd infra && terraform output -raw webhook_url`)

_register-webhook webhook_url:
    curl -s "https://api.telegram.org/bot${BOT_TOKEN}/setWebhook?url={{webhook_url}}"
