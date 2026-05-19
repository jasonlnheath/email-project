import SwiftUI

struct SettingsView: View {
    // MARK: - LLM Provider State
    @State private var selectedProvider: LLMProviderType = .anthropic
    @State private var anthropicBaseURL: String = ""
    @State private var anthropicModel: String = ""
    @State private var anthropicKey: String = ""
    @State private var showAnthropicKey: Bool = false
    @State private var openAIBaseURL: String = ""
    @State private var openAIKey: String = ""
    @State private var openAIModel: String = ""
    @State private var showOpenAIKey: Bool = false
    @State private var saveMessage: String?

    // MARK: - Appearance State
    @State private var selectedTheme: AppTheme = .system

    // MARK: - OAuth State
    @State private var isSignedIn = false
    @State private var userEmail: String?

    // MARK: - Contacts State
    @StateObject private var contactsVM = ContactsViewModel()

    var body: some View {
        NavigationStack {
            Form {
                // MARK: - LLM Providers Section
                Section("LLM Providers") {
                    Picker("Active Provider", selection: $selectedProvider) {
                        ForEach(LLMProviderType.allCases) { type in
                            Text(type.rawValue).tag(type)
                        }
                    }
                    .pickerStyle(.segmented)

                    switch selectedProvider {
                    case .anthropic:
                        AnthropicProviderSettings(
                            baseURL: $anthropicBaseURL,
                            model: $anthropicModel,
                            apiKey: $anthropicKey,
                            showKey: $showAnthropicKey,
                            saveMessage: $saveMessage
                        )
                    case .openai:
                        OpenAIProviderSettings(
                            baseURL: $openAIBaseURL,
                            apiKey: $openAIKey,
                            model: $openAIModel,
                            showKey: $showOpenAIKey,
                            saveMessage: $saveMessage
                        )
                    }
                }

                // MARK: - Appearance Section
                Section("Appearance") {
                    Picker("Theme", selection: $selectedTheme) {
                        ForEach(AppTheme.allCases, id: \.self) { theme in
                            Text(theme.displayName).tag(theme)
                        }
                    }
                    .pickerStyle(.segmented)
                    .onChange(of: selectedTheme) { newTheme in
                        AppTheme.current = newTheme
                    }
                }

                // MARK: - Gmail Account Section
                Section("Gmail Account") {
                    if isSignedIn {
                        LabeledContent("Signed in as", value: userEmail ?? "Unknown")

                        Button("Sign Out") {
                            Task {
                                await signOut()
                            }
                        }
                        .foregroundColor(.red)
                    } else {
                        Button("Sign in with Google") {
                            // TODO: Navigate to LoginView or trigger Google Sign-In
                        }
                    }
                }

                // MARK: - Contacts Section
                Section("Contacts") {
                    if contactsVM.isSyncing {
                        HStack {
                            ProgressView()
                                .scaleEffect(0.8)
                            Text("Syncing...")
                                .foregroundColor(.secondary)
                        }
                    } else {
                        LabeledContent("Total Contacts", value: "\(contactsVM.contacts.count)")
                        if let lastSync = contactsVM.lastSync {
                            LabeledContent("Last Sync", value: lastSync.formatted(date: .abbreviated, time: .shortened))
                        }
                        Button("Refresh Contacts") {
                            Task {
                                await contactsVM.syncContacts()
                            }
                        }
                    }
                }

                // MARK: - About Section
                Section("About") {
                    LabeledContent("Version", value: "1.0.0")
                    LabeledContent("Context Budget", value: "\(Constants.contextBudgetTokens) tokens")
                }
            }
            .navigationTitle("Settings")
        }
        .onAppear {
            Task { @MainActor in
                await loadSettings()
            }
        }
        .onChange(of: selectedProvider) { newType in
            LLMProviderFactory.shared.setSelectedProviderType(newType)
        }
    }

    // MARK: - Actions

    private func loadSettings() async {
        // Load LLM Provider settings
        selectedProvider = LLMProviderFactory.shared.getSelectedProviderType()
        anthropicBaseURL = UserDefaults.standard.string(forKey: Constants.anthropicBaseURLKey) ?? Constants.anthropicBaseURLDefault
        anthropicModel = UserDefaults.standard.string(forKey: Constants.anthropicModelKey) ?? Constants.anthropicModelDefault
        anthropicKey = KeychainService.shared.load(key: Constants.keychainAnthropicKey) ?? ""
        openAIBaseURL = UserDefaults.standard.string(forKey: Constants.openaiBaseURLKey) ?? Constants.openaiBaseURLDefault
        openAIKey = KeychainService.shared.load(key: Constants.keychainOpenAIKey) ?? ""
        openAIModel = UserDefaults.standard.string(forKey: Constants.openaiModelKey) ?? Constants.openaiModelDefault

        // Load Appearance settings
        selectedTheme = AppTheme.current

        // Load OAuth settings
        isSignedIn = await OAuthService.shared.isSignedIn
        userEmail = await OAuthService.shared.currentUserEmail

        // Load contacts (StateObject initializes automatically)
    }

    private func signOut() async {
        do {
            try await OAuthService.shared.signOut()
            isSignedIn = false
            userEmail = nil
            contactsVM.contacts = []
            contactsVM.lastSync = nil
        } catch {
            saveMessage = "Sign out error: \(error.localizedDescription)"
        }
    }
}

// MARK: - Anthropic Provider Settings

struct AnthropicProviderSettings: View {
    @Binding var baseURL: String
    @Binding var model: String
    @Binding var apiKey: String
    @Binding var showKey: Bool
    @Binding var saveMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Anthropic Claude")
                .font(.headline)

            TextField("Base URL", text: $baseURL)
                .autocapitalization(.none)
                .disableAutocorrection(true)

            TextField("Model", text: $model)
                .autocapitalization(.none)
                .disableAutocorrection(true)

            HStack {
                if showKey {
                    TextField("API Key", text: $apiKey)
                        .textContentType(.password)
                } else {
                    SecureField("API Key", text: $apiKey)
                }
                Button(action: { showKey.toggle() }) {
                    Image(systemName: showKey ? "eye.slash" : "eye")
                }
            }

            Button("Save Configuration") {
                saveAnthropicConfig()
            }
            .disabled(apiKey.isEmpty || baseURL.isEmpty || model.isEmpty)

            if let message = saveMessage {
                Text(message)
                    .font(.caption)
                    .foregroundColor(message == "Saved!" ? .green : .red)
            }

            Text("Compatible with Anthropic Claude and Z.AI GLM models")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 8)
    }

    private func saveAnthropicConfig() {
        do {
            try KeychainService.shared.save(key: Constants.keychainAnthropicKey, value: apiKey)
            UserDefaults.standard.set(baseURL, forKey: Constants.anthropicBaseURLKey)
            UserDefaults.standard.set(model, forKey: Constants.anthropicModelKey)
            saveMessage = "Saved!"
        } catch {
            saveMessage = "Error: \(error.localizedDescription)"
        }
    }
}

// MARK: - OpenAI Provider Settings

struct OpenAIProviderSettings: View {
    @Binding var baseURL: String
    @Binding var apiKey: String
    @Binding var model: String
    @Binding var showKey: Bool
    @Binding var saveMessage: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("OpenAI-Compatible")
                .font(.headline)

            TextField("Base URL", text: $baseURL)
                .autocapitalization(.none)
                .disableAutocorrection(true)

            HStack {
                if showKey {
                    TextField("API Key", text: $apiKey)
                        .textContentType(.password)
                } else {
                    SecureField("API Key", text: $apiKey)
                }
                Button(action: { showKey.toggle() }) {
                    Image(systemName: showKey ? "eye.slash" : "eye")
                }
            }

            TextField("Model", text: $model)
                .autocapitalization(.none)
                .disableAutocorrection(true)

            Button("Save Configuration") {
                saveOpenAIConfig()
            }
            .disabled(baseURL.isEmpty || apiKey.isEmpty || model.isEmpty)

            if let message = saveMessage {
                Text(message)
                    .font(.caption)
                    .foregroundColor(message == "Saved!" ? .green : .red)
            }

            Text("Compatible with OpenAI, Qwen, and other models")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .padding(.vertical, 8)
    }

    private func saveOpenAIConfig() {
        do {
            try KeychainService.shared.save(key: Constants.keychainOpenAIKey, value: apiKey)
            UserDefaults.standard.set(baseURL, forKey: Constants.openaiBaseURLKey)
            UserDefaults.standard.set(model, forKey: Constants.openaiModelKey)
            saveMessage = "Saved!"
        } catch {
            saveMessage = "Error: \(error.localizedDescription)"
        }
    }
}

struct SettingsView_Previews: PreviewProvider {
    static var previews: some View {
        SettingsView()
    }
}
