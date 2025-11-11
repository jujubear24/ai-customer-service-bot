const synthetics = require("Synthetics");
const log = require("SyntheticsLogger");
const https = require("https");

/**
 * API Health Check Canary
 *
 * This canary monitors the health of the AI Customer Service Bot API.
 * It performs a simple GET request to the /health endpoint and validates
 * the response status and structure.
 */

const apiUrl = process.env.API_URL || "https://api.example.com";
const healthEndpoint = "/health";
const requestTimeout = 10000; // 10 seconds

/**
 * Makes an HTTPS request to the health endpoint
 * @returns {Promise<Object>} Response object with status and body
 */
async function checkHealth() {
  return new Promise((resolve, reject) => {
    const url = new URL(healthEndpoint, apiUrl);

    log.info(`Making request to: ${url.toString()}`);

    const options = {
      hostname: url.hostname,
      port: 443,
      path: url.pathname,
      method: "GET",
      headers: {
        "User-Agent": "CloudWatch-Synthetics",
        "Content-Type": "application/json",
      },
      timeout: requestTimeout,
    };

    const req = https.request(options, (res) => {
      let data = "";

      res.on("data", (chunk) => {
        data += chunk;
      });

      res.on("end", () => {
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body: data,
        });
      });
    });

    req.on("error", (error) => {
      reject(error);
    });

    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`Request timeout after ${requestTimeout}ms`));
    });

    req.end();
  });
}

/**
 * Validates the health check response
 * @param {Object} response - The HTTP response object
 * @throws {Error} If validation fails
 */
function validateResponse(response) {
  // Check status code
  if (response.statusCode !== 200) {
    throw new Error(
      `Health check failed with status code: ${response.statusCode}`
    );
  }

  // Parse and validate response body
  let body;
  try {
    body = JSON.parse(response.body);
  } catch (error) {
    throw new Error(`Invalid JSON response: ${error.message}`);
  }

  // Validate expected response structure
  if (!body.status || body.status !== "healthy") {
    throw new Error(`Unexpected health status: ${body.status}`);
  }

  log.info("Health check passed successfully", { response: body });
}

/**
 * Main handler function
 */
exports.handler = async function () {
  log.info("Starting API health check canary");
  log.info(`Target API: ${apiUrl}`);

  try {
    // TODO: Remove this placeholder once API Gateway is deployed
    if (apiUrl === "https://api.example.com") {
      log.warn(
        "Using placeholder API URL - canary will pass without real check"
      );
      log.info(
        "Update API_URL environment variable once API Gateway is deployed"
      );
      return "Success - Placeholder mode";
    }

    // Perform health check
    const response = await checkHealth();

    // Validate response
    validateResponse(response);

    log.info("Canary completed successfully");
    return "Success";
  } catch (error) {
    log.error("Canary failed", {
      error: error.message,
      stack: error.stack,
    });
    throw error; // Re-throw to mark canary as failed
  }
};
