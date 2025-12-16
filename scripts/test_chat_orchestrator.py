import argparse
import json
import sys

import boto3
from botocore.exceptions import ClientError


def test_chat_orchestrator(
    project_name: str, environment: str, message: str, use_rag: bool
) -> None:
    """
    Invokes the deployed Chat Orchestrator Lambda function directly.
    """
    lambda_client = boto3.client("lambda")

    # Pattern: {project}-{function}-{environment}
    function_name = f"{project_name}-chat-orchestrator-{environment}"

    print(f"🔎 Target Function: {function_name}")
    print(f"💬 Message: '{message}' (RAG: {use_rag})")

    payload = {
        "body": json.dumps(
            {
                "message": message,
                "tenant_id": "e2e-test-tenant",
                "conversation_id": "e2e-test-conv-001",
                "use_rag": use_rag,
                "rag_options": {"top_k": 2, "min_score": 0.5},
            }
        )
    }

    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="RequestResponse",
            Payload=json.dumps(payload),
        )

        raw_payload = response["Payload"].read().decode("utf-8")
        result = json.loads(raw_payload)

        # Check for function error (unhandled exception)
        if "FunctionError" in response:
            print(f"❌ Lambda Function Error: {result}")
            sys.exit(1)

        # Check for Lambda/API Gateway wrapper status code
        if "statusCode" in result:
            if result["statusCode"] != 200:
                print(f"❌ Error: Received status code {result['statusCode']}")
                print(f"Body: {result.get('body')}")
                sys.exit(1)
            body = json.loads(result["body"])
        else:
            body = result

        print("\n✅ Response Received:")
        print(json.dumps(body, indent=2))

        # Validation
        if body.get("response"):
            print("\n[Pass] Response text present.")
        else:
            print("\n[Fail] No response text found.")
            sys.exit(1)

        if use_rag:
            sources = body.get("sources", [])
            print(f"[Info] Sources returned: {len(sources)}")
            for s in sources:
                print(f"  - {s.get('name')} (score: {s.get('score')})")

        metadata = body.get("metadata", {})
        latency = metadata.get("latency", {})
        print(
            f"\n⏱️  Latency: Total={latency.get('total_ms', 'N/A')}ms "
            f"(Bedrock={latency.get('bedrock_ms', 'N/A')}ms)"
        )

        print("\n🎉 E2E Test Passed!")

    except ClientError as e:
        print(f"❌ AWS Client Error: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"❌ JSON Parse Error: {e}")
        print(f"Raw response: {raw_payload}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Unexpected Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="E2E Test for Chat Orchestrator")
    parser.add_argument("--project", default="ai-customer-service-bot", help="Project name")
    parser.add_argument("--env", default="dev", help="Environment (dev/prod)")
    parser.add_argument("--message", default="How do I reset my password?", help="Test message")
    parser.add_argument("--no-rag", action="store_true", help="Disable RAG")

    args = parser.parse_args()

    test_chat_orchestrator(
        project_name=args.project,
        environment=args.env,
        message=args.message,
        use_rag=not args.no_rag,
    )
