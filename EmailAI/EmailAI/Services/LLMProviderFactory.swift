import Foundation

/// Factory for creating and managing LLM providers
class LLMProviderFactory {
    static let shared = LLMProviderFactory()

    private init() {}

    // MARK: - Provider Creation

    /// Create a provider based on the specified type
    func createProvider(type: LLMProviderType) -> LLMProvider {
        switch type {
        case .anthropic:
            return createAnthropicProvider()
        case .openai:
            return createOpenAIProvider()
        }
    }

    /// Create an Anthropic provider with API key from keychain
    func getAnthropicProvider() -> LLMProvider {
        return createAnthropicProvider()
    }

    /// Create an OpenAI provider with configuration from UserDefaults/keychain
    func getOpenAIProvider() -> LLMProvider {
        return createOpenAIProvider()
    }

    // MARK: - Provider Selection

    /// Get the currently selected provider type from UserDefaults
    func getSelectedProviderType() -> LLMProviderType {
        let rawValue = UserDefaults.standard.string(forKey: Constants.selectedLLMProviderKey) ?? LLMProviderType.anthropic.rawValue
        return LLMProviderType(rawValue: rawValue) ?? .anthropic
    }

    /// Set the selected provider type in UserDefaults
    func setSelectedProviderType(_ type: LLMProviderType) {
        UserDefaults.standard.set(type.rawValue, forKey: Constants.selectedLLMProviderKey)
    }

    /// Get the currently selected provider instance
    func getSelectedProvider() -> LLMProvider {
        let selectedType = getSelectedProviderType()
        return createProvider(type: selectedType)
    }

    // MARK: - Private Helpers

    private func createAnthropicProvider() -> LLMProvider {
        // Get configuration from UserDefaults
        let baseURL = UserDefaults.standard.string(forKey: Constants.anthropicBaseURLKey) ?? Constants.anthropicBaseURLDefault
        let model = UserDefaults.standard.string(forKey: Constants.anthropicModelKey) ?? Constants.anthropicModelDefault
        // The AnthropicProvider manages its own API key retrieval from keychain
        return AnthropicProvider(baseURL: baseURL, model: model)
    }

    private func createOpenAIProvider() -> LLMProvider {
        // Get configuration from UserDefaults and keychain
        let baseURL = UserDefaults.standard.string(forKey: Constants.openaiBaseURLKey) ?? Constants.openaiBaseURLDefault

        // Try to get API key from keychain, fallback to empty string
        let apiKey = KeychainService.shared.load(key: Constants.keychainOpenAIKey) ?? ""

        let model = UserDefaults.standard.string(forKey: Constants.openaiModelKey) ?? Constants.openaiModelDefault

        return OpenAIProvider(baseURL: baseURL, apiKey: apiKey, model: model)
    }
}
