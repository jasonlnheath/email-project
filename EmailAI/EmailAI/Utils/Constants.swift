import Foundation

enum Constants {
    // API Endpoints
    static let anthropicBaseURL = "https://api.anthropic.com"
    static let anthropicBaseURLDefault = "https://api.anthropic.com"
    static let anthropicModelDefault = "claude-sonnet-4-20250514"

    // OpenAI defaults (can be overridden via UserDefaults)
    static let openaiBaseURLDefault = "https://api.openai.com/v1"
    static let openaiModelDefault = "gpt-4o"

    // Gmail API
    static let gmailScopes = ["https://www.googleapis.com/auth/gmail.readonly"]
    static let contactsScopes = ["https://www.googleapis.com/auth/contacts.readonly"]

    // Embedding
    static let embeddingDim = 1536

    // Tier sizes
    static let tier1Count = 50      // raw emails
    static let tier2MaxCount = 400  // summarized emails
    static let contextBudgetTokens = 64000

    // Keychain keys
    static let keychainAnthropicKey = "com.emailai.anthropic-key"
    static let keychainOpenAIKey = "com.emailai.openai-key"
    static let keychainGmailAccessToken = "com.emailai.gmail-access-token"
    static let keychainGmailRefreshToken = "com.emailai.gmail-refresh-token"
    static let keychainGmailTokenExpiry = "com.emailai.gmail-token-expiry"

    // UserDefaults keys
    static let anthropicBaseURLKey = "com.emailai.anthropic-baseurl"
    static let anthropicModelKey = "com.emailai.anthropic-model"
    static let openaiBaseURLKey = "com.emailai.openai-baseurl"
    static let openaiModelKey = "com.emailai.openai-model"
    static let selectedLLMProviderKey = "com.emailai.selected-llm-provider"
}
