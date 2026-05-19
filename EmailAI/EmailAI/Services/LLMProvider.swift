import Foundation

/// Protocol for LLM providers (Anthropic, OpenAI, etc.)
protocol LLMProvider {
    /// Send a chat completion request and return the response text
    func chat(messages: [[String: String]], systemPrompt: String?) async throws -> String

    /// Summarize a single email and return structured results
    func summarizeEmail(subject: String, sender: String, body: String) async throws -> SummarizeResult
}

/// Available LLM provider types
enum LLMProviderType: String, CaseIterable, Identifiable {
    case anthropic = "Anthropic"
    case openai = "OpenAI"

    var id: String { rawValue }
}

/// Result of email summarization
struct SummarizeResult: Codable {
    let summaryPurpose: String
    let keyEntities: [String]
    let actionItems: [String]
    let sentiment: String
}

/// LLM-related errors
enum LLMError: LocalizedError {
    case missingAPIKey
    case apiError(statusCode: Int, body: String)

    var errorDescription: String? {
        switch self {
        case .missingAPIKey:
            return "API key not set. Go to Settings to add your API key."
        case .apiError(let code, let body):
            return "API error (\(code)): \(body.prefix(200))"
        }
    }
}
