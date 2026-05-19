import SwiftUI

struct ContentView: View {
    @State private var selectedTab = 0
    @StateObject private var emailListVM = EmailListViewModel()
    @StateObject private var searchVM = SearchViewModel()
    @StateObject private var chatVM = ChatViewModel()

    var body: some View {
        TabView(selection: $selectedTab) {
            // Dashboard - quick processing of unread emails
            DashboardView()
                .tabItem {
                    Label("Dashboard", systemImage: "tray.full")
                }
                .tag(0)

            // Emails - simple mail client
            EmailListView()
                .environmentObject(emailListVM)
                .tabItem {
                    Label("Emails", systemImage: "envelope")
                }
                .tag(1)

            // Chat
            ChatView()
                .environmentObject(emailListVM)
                .environmentObject(chatVM)
                .tabItem {
                    Label("Chat", systemImage: "bubble.left.and.bubble.right")
                }
                .tag(2)

            // Contacts
            ContactsView()
                .tabItem {
                    Label("Contacts", systemImage: "person.2")
                }
                .tag(3)

            // Settings
            SettingsView()
                .tabItem {
                    Label("Settings", systemImage: "gearshape")
                }
                .tag(4)
        }
    }
}

struct ContentView_Previews: PreviewProvider {
    static var previews: some View {
        ContentView()
    }
}
