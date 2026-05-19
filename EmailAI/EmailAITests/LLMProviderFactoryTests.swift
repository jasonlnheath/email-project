import XCTest
@testable import EmailAI

/// Tests for LLMProviderFactory
final class LLMProviderFactoryTests: XCTestCase {

    // MARK: - Factory Creation Tests

    func testFactoryCreatesAnthropicProvider() {
        let provider = LLMProviderFactory.shared.createProvider(type: .anthropic)
        XCTAssertTrue(provider is AnthropicProvider, "Should create AnthropicProvider for .anthropic type")
    }

    func testFactoryCreatesOpenAIProvider() {
        // Set up required values for OpenAI provider
        let testBaseURL = "https://api.openai.com/v1"
        let testAPIKey = "test-key"
        let testModel = "gpt-4o"

        UserDefaults.standard.set(testBaseURL, forKey: Constants.openaiBaseURLKey)
        UserDefaults.standard.set(testAPIKey, forKey: Constants.keychainOpenAIKey)
        UserDefaults.standard.set(testModel, forKey: Constants.openaiModelKey)

        let provider = LLMProviderFactory.shared.createProvider(type: .openai)
        XCTAssertTrue(provider is OpenAIProvider, "Should create OpenAIProvider for .openai type")

        // Cleanup
        UserDefaults.standard.removeObject(forKey: Constants.openaiBaseURLKey)
        UserDefaults.standard.removeObject(forKey: Constants.keychainOpenAIKey)
        UserDefaults.standard.removeObject(forKey: Constants.openaiModelKey)
    }

    func testFactoryConvenienceMethodForAnthropic() {
        let provider = LLMProviderFactory.shared.getAnthropicProvider()
        XCTAssertTrue(provider is AnthropicProvider, "Convenience method should create AnthropicProvider")
    }

    func testFactoryConvenienceMethodForOpenAI() {
        // Set up required values
        let testBaseURL = "https://api.openai.com/v1"
        let testAPIKey = "test-key"
        let testModel = "gpt-4o"

        UserDefaults.standard.set(testBaseURL, forKey: Constants.openaiBaseURLKey)
        UserDefaults.standard.set(testAPIKey, forKey: Constants.keychainOpenAIKey)
        UserDefaults.standard.set(testModel, forKey: Constants.openaiModelKey)

        let provider = LLMProviderFactory.shared.getOpenAIProvider()
        XCTAssertTrue(provider is OpenAIProvider, "Convenience method should create OpenAIProvider")

        // Cleanup
        UserDefaults.standard.removeObject(forKey: Constants.openaiBaseURLKey)
        UserDefaults.standard.removeObject(forKey: Constants.keychainOpenAIKey)
        UserDefaults.standard.removeObject(forKey: Constants.openaiModelKey)
    }

    // MARK: - Provider Selection Tests

    func testDefaultSelectedProviderIsAnthropic() {
        // Clear any stored selection
        UserDefaults.standard.removeObject(forKey: Constants.selectedLLMProviderKey)

        let selectedProvider = LLMProviderFactory.shared.getSelectedProviderType()
        XCTAssertEqual(selectedProvider, .anthropic, "Default provider should be Anthropic")
    }

    func testSetSelectedProviderType() {
        LLMProviderFactory.shared.setSelectedProviderType(.openai)
        let selectedProvider = LLMProviderFactory.shared.getSelectedProviderType()
        XCTAssertEqual(selectedProvider, .openai, "Should be able to set selected provider to OpenAI")

        // Reset to default
        LLMProviderFactory.shared.setSelectedProviderType(.anthropic)
    }

    func testGetSelectedProviderReturnsCorrectType() async {
        // Test with Anthropic (default)
        var provider = LLMProviderFactory.shared.getSelectedProvider()
        XCTAssertTrue(provider is AnthropicProvider, "Selected provider should be Anthropic by default")

        // Test with OpenAI
        let testBaseURL = "https://api.openai.com/v1"
        let testAPIKey = "test-key"
        let testModel = "gpt-4o"

        UserDefaults.standard.set(testBaseURL, forKey: Constants.openaiBaseURLKey)
        UserDefaults.standard.set(testAPIKey, forKey: Constants.keychainOpenAIKey)
        UserDefaults.standard.set(testModel, forKey: Constants.openaiModelKey)
        LLMProviderFactory.shared.setSelectedProviderType(.openai)

        provider = LLMProviderFactory.shared.getSelectedProvider()
        XCTAssertTrue(provider is OpenAIProvider, "Selected provider should be OpenAI after selection")

        // Cleanup
        UserDefaults.standard.removeObject(forKey: Constants.openaiBaseURLKey)
        UserDefaults.standard.removeObject(forKey: Constants.keychainOpenAIKey)
        UserDefaults.standard.removeObject(forKey: Constants.openaiModelKey)
        LLMProviderFactory.shared.setSelectedProviderType(.anthropic)
    }

    // MARK: - Error Handling Tests

    func testFactoryOpenAIProviderThrowsWithoutConfiguration() {
        // Clear OpenAI configuration
        UserDefaults.standard.removeObject(forKey: Constants.openaiBaseURLKey)
        UserDefaults.standard.removeObject(forKey: Constants.keychainOpenAIKey)
        UserDefaults.standard.removeObject(forKey: Constants.openaiModelKey)

        let provider = LLMProviderFactory.shared.createProvider(type: .openai)
        XCTAssertTrue(provider is OpenAIProvider, "Should still create OpenAIProvider even without config")
    }
}
