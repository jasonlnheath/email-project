import SwiftUI
import GoogleSignIn

// Helper to read Info.plist values
enum InfoPlistReader {
    static var gidClientID: String {
        guard let clientID = Bundle.main.object(forInfoDictionaryKey: "GIDClientID") as? String else {
            fatalError("GIDClientID not found in Info.plist")
        }
        return clientID
    }
}

struct LoginView: View {
    @State private var isSigningIn = false
    @State private var errorMessage: String?
    @Environment(\.dismiss) private var dismiss
    @AppStorage("isSignedIn") private var isSignedIn = false

    var body: some View {
        GeometryReader { geometry in
            VStack(spacing: 30) {
                Spacer()

                Image(systemName: "envelope.badge.fill")
                    .font(.system(size: 60))
                    .foregroundStyle(.blue)

                Text("Email AI")
                    .font(.largeTitle)
                    .fontWeight(.bold)

                Text("Your emails, summarized and searchable with AI")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .multilineTextAlignment(.center)
                    .padding(.horizontal)

                // Google Sign-In button
                Button(action: handleSignIn) {
                    HStack {
                        Image(systemName: "g.circle.fill")
                            .font(.title2)
                        Text("Sign in with Google")
                            .font(.headline)
                    }
                    .foregroundStyle(.white)
                    .frame(maxWidth: .infinity)
                    .padding()
                    .background(Color.red)
                    .clipShape(RoundedRectangle(cornerRadius: 8))
                }
                .disabled(isSigningIn)
                .frame(height: 50)
                .padding(.horizontal, 40)

                // Loading indicator
                if isSigningIn {
                    ProgressView()
                        .scaleEffect(0.8)
                }

                // Error message
                if let error = errorMessage {
                    Text(error)
                        .font(.caption)
                        .foregroundStyle(.red)
                        .padding(.horizontal)
                }

                // Dev mode for testing
                VStack(spacing: 8) {
                    Text("Development")
                        .font(.caption2)
                        .foregroundStyle(.secondary)

                    Button("Skip OAuth (Dev Mode)") {
                        handleDevMode()
                    }
                    .font(.caption)
                    .foregroundStyle(.secondary)
                }

                Spacer()
            }
            .padding()
        }
    }

    private func handleSignIn() {
        print("=== Sign-in button tapped ===")
        isSigningIn = true
        errorMessage = nil

        // Get root view controller
        guard let windowScene = UIApplication.shared.connectedScenes.first as? UIWindowScene,
              let rootViewController = windowScene.windows.first?.rootViewController else {
            print("ERROR: Unable to get root view controller")
            errorMessage = "Unable to present sign-in"
            isSigningIn = false
            return
        }

        print("Got root view controller")

        // Create configuration
        let config = GIDConfiguration(clientID: InfoPlistReader.gidClientID)

        // Perform sign-in with Gmail and Contacts scopes
        GIDSignIn.sharedInstance.signIn(with: config, presenting: rootViewController, hint: nil, additionalScopes: ["https://www.googleapis.com/auth/gmail.modify", "https://www.googleapis.com/auth/contacts.readonly"]) { result, error in
            print("=== Sign-in callback ===")
            print("Error: \(error?.localizedDescription ?? "none")")
            print("Result: \(result?.description ?? "none")")

            DispatchQueue.main.async {
                if let error = error {
                    self.errorMessage = "Sign-in failed: \(error.localizedDescription)"
                    self.isSigningIn = false
                    return
                }

                guard let user = result else {
                    self.errorMessage = "Failed to get user data"
                    self.isSigningIn = false
                    return
                }

                let accessToken = user.authentication.accessToken
                let userEmail = user.profile?.email ?? "unknown@gmail.com"
                let refreshToken = user.authentication.refreshToken
                let expirationDate = Date().addingTimeInterval(3600)

                print("Storing tokens for: \(userEmail)")

                Task {
                    do {
                        try await OAuthService.shared.storeTokens(
                            accessToken: accessToken,
                            refreshToken: refreshToken,
                            expirationDate: expirationDate,
                            userEmail: userEmail
                        )
                        print("Tokens stored!")
                        await MainActor.run {
                            self.isSignedIn = true
                        }
                    } catch {
                        print("Failed to store: \(error)")
                        await MainActor.run {
                            self.errorMessage = "Failed to store: \(error.localizedDescription)"
                            self.isSigningIn = false
                        }
                    }
                }
            }
        }
    }

    private func handleDevMode() {
        print("=== Dev mode tapped ===")
        Task {
            do {
                let expiryDate = Date().addingTimeInterval(3600)
                try await OAuthService.shared.storeTokens(
                    accessToken: "dev_access_token",
                    refreshToken: "dev_refresh_token",
                    expirationDate: expiryDate,
                    userEmail: "dev@example.com"
                )
                print("Dev mode success")
                isSignedIn = true
            } catch {
                print("Dev mode failed: \(error)")
                errorMessage = error.localizedDescription
            }
        }
    }
}

struct LoginView_Previews: PreviewProvider {
    static var previews: some View {
        LoginView()
    }
}
