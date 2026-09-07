import SwiftUI
import PhotosUI

@MainActor final class AssistantModel: ObservableObject {
    @Published var endpoint = "https://"
    @Published var code = ""
    @Published var text = ""
    @Published var draft = ""
    @Published var status = "请在电脑生成配对码"
    @Published var people: [[String: String]] = []
    @Published var personID = ""
    @Published var goal = "自然接话"
    @Published var mode = "local"
    @Published var approved = false
    @Published var candidates: [String] = []
    @Published var image: UIImage?
    @Published var busy = false
    private var connection = DeviceVault.load()
    private var result: [String: Any]?
    private var context = UUID().uuidString
    private var revision = 0
    init() { if let connection { endpoint = connection.endpoint } }
    func invalidate() {
        let old = context; context = UUID().uuidString; revision += 1; result = nil; candidates = []; draft = ""; approved = false; try? LeaseStore.clear()
        if let c = connection { Task { _ = try? await NativeHTTP.call(endpoint: c.endpoint, path: "cancel", token: c.token, body: ["context": old]) } }
    }
    func pair() async {
        await task {
            let response = try await NativeHTTP.call(endpoint: self.endpoint, path: "pair", body: ["code": self.code, "name": "iPhone"])
            guard let token = response["token"] as? String else { throw LensError.message("配对响应无效") }
            let c = DeviceConnection(endpoint: self.endpoint, token: token); try DeviceVault.save(c); self.connection = c; self.code = ""
            try await self.roster()
        }
    }
    func roster() async throws {
        guard let c = connection else { return }
        let response = try await NativeHTTP.call(endpoint: c.endpoint, path: "roster", token: c.token)
        people = response["people"] as? [[String: String]] ?? []
        if !people.contains(where: { $0["id"] == personID }) { personID = people.first?["id"] ?? "" }
        status = "已连接，选择人物并批准片段"
    }
    func analyze() async {
        guard approved, let c = connection, let person = people.first(where: { $0["id"] == personID }) else { status = "请连接、选择人物并批准片段"; return }
        let input = text; invalidate(); let generation = revision; let nonce = context
        await task {
            let response = try await NativeHTTP.call(endpoint: c.endpoint, path: "analyze", token: c.token, body: ["context": nonce, "host": "ios.user-confirmed", "person_id": self.personID, "pair_id": person["pair_id"] ?? "", "text": input, "goal": self.goal, "mode": self.mode, "approved": true])
            guard generation == self.revision else { return }
            self.result = response; self.candidates = (response["candidates"] as? [[String: String]] ?? []).compactMap { $0["text"] }
            self.status = response["summary"] as? String ?? "分析完成"
        }
    }
    func stage() async {
        guard let c = connection, let result, let ticket = result["ticket_id"] as? String, let person = result["person"] as? [String: String], !draft.isEmpty else { status = "请先分析并选择草稿"; return }
        let generation = revision
        await task {
            let response = try await NativeHTTP.call(endpoint: c.endpoint, path: "tickets/\(ticket)/lease", token: c.token, body: ["context": self.context, "host": "ios.user-confirmed", "person_id": person["id"] ?? "", "pair_id": person["pair_id"] ?? "", "draft": self.draft, "approved": true])
            guard generation == self.revision else { return }
            var lease = try JSONDecoder().decode(InsertionLease.self, from: JSONSerialization.data(withJSONObject: response)); lease.endpoint = c.endpoint
            try LeaseStore.save(lease); self.status = "30 秒内返回聊天，切换观微键盘，核对人物后插入。"
        }
    }
    func extract() async {
        guard let image, let c = connection else { status = "请先选择截图并连接服务"; return }
        invalidate(); let generation = revision; let nonce = context
        await task {
            let scale = min(1, 1600 / max(image.size.width, image.size.height))
            let format = UIGraphicsImageRendererFormat(); format.scale = 1
            let resized = UIGraphicsImageRenderer(size: CGSize(width: image.size.width * scale, height: image.size.height * scale), format: format).image { _ in image.draw(in: CGRect(origin: .zero, size: CGSize(width: image.size.width * scale, height: image.size.height * scale))) }
            guard let data = resized.jpegData(compressionQuality: 0.85) else { throw LensError.message("图片无法转换") }
            let response = try await NativeHTTP.call(endpoint: c.endpoint, path: "extract", token: c.token, body: ["context": nonce, "host": "ios.user-confirmed", "approved": true, "image": "data:image/jpeg;base64," + data.base64EncodedString()])
            guard generation == self.revision else { return }
            self.text = response["text"] as? String ?? ""; self.image = nil; self.status = "请核对说话人和原话，再批准分析。"
        }
    }
    func disconnect() { invalidate(); connection = nil; DeviceVault.clear(); image = nil; text = ""; people = []; status = "已清除本机连接；电脑可撤销设备授权" }
    func task(_ action: () async throws -> Void) async {
        guard !busy else { return }; busy = true; defer { busy = false }
        do { try await action() } catch { status = error.localizedDescription }
    }
}

@main struct LensApp: App {
    @StateObject private var model = AssistantModel()
    @State private var photo: PhotosPickerItem?
    var body: some Scene {
        WindowGroup {
            NavigationStack {
                Form {
                    Section("设备连接") {
                        TextField("HTTPS 服务根地址", text: $model.endpoint).textInputAutocapitalization(.never).autocorrectionDisabled().accessibilityIdentifier("endpoint")
                        SecureField("六位配对码", text: $model.code).keyboardType(.numberPad)
                        Button("配对连接") { Task { await model.pair() } }.disabled(model.busy)
                        Button("断开连接") { model.disconnect() }.accessibilityIdentifier("disconnect")
                        Text(model.status).accessibilityIdentifier("status")
                    }
                    Section("你批准的聊天片段") {
                        Picker("人物", selection: $model.personID) { ForEach(model.people, id: \.self) { p in Text(p["name"] ?? "").tag(p["id"] ?? "") } }
                        Picker("目标", selection: $model.goal) { ForEach(["自然接话", "关心近况", "修复误会", "表达边界"], id: \.self) { Text($0) } }
                        Picker("分析", selection: $model.mode) { Text("规则试算").tag("local"); Text("GPT").tag("model") }
                        TextEditor(text: $model.text).autocorrectionDisabled().textInputAutocapitalization(.never).frame(minHeight: 130).accessibilityIdentifier("transcript")
                        PhotosPicker("选择一张截图", selection: $photo, matching: .images)
                        if let image = model.image {
                            Image(uiImage: image).resizable().scaledToFit().frame(maxHeight: 280)
                            Button("批准此图并转写") { Task { await model.extract() } }.disabled(model.busy)
                            Button("丢弃图片") { model.image = nil; model.invalidate() }
                        }
                        Toggle("已核对人物和片段，同意提交服务", isOn: $model.approved).accessibilityIdentifier("approval")
                        Button("分析已批准片段") { Task { await model.analyze() } }.disabled(model.busy).accessibilityIdentifier("analyze")
                    }
                    Section("候选与插入") {
                        ForEach(model.candidates, id: \.self) { text in Button(text) { model.draft = text } }
                        TextEditor(text: $model.draft).frame(minHeight: 90).accessibilityIdentifier("draft")
                        Button("批准草稿并交给键盘（30 秒）") { Task { await model.stage() } }.disabled(model.busy)
                        Text("在系统设置启用观微建议键盘。允许完全访问后，键盘仅在你点击确认插入时联网兑换这一次短期授权；不上传按键或读取聊天全文。中文输入可随时切回熟悉的系统键盘。")
                    }
                }.navigationTitle("观微")
                    .scrollDismissesKeyboard(.interactively)
                    .toolbar {
                        ToolbarItemGroup(placement: .keyboard) {
                            Spacer()
                            Button("完成输入") { UIApplication.shared.sendAction(#selector(UIResponder.resignFirstResponder), to: nil, from: nil, for: nil) }.accessibilityIdentifier("finishInput")
                        }
                    }
                    .task { try? await model.roster() }
                    .onChange(of: model.text) { _, _ in model.invalidate() }
                    .onChange(of: model.personID) { _, _ in model.invalidate() }
                    .onChange(of: model.goal) { _, _ in model.invalidate() }
                    .onChange(of: model.mode) { _, _ in model.invalidate() }
                    .onChange(of: photo) { _, value in
                        model.invalidate(); model.image = nil
                        Task { if let data = try? await value?.loadTransferable(type: Data.self), photo == value, data.count <= 15_000_000 { model.image = UIImage(data: data) } }
                    }
            }
        }
    }
}
