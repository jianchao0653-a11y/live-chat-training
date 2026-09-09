import UIKit

final class KeyboardViewController: UIInputViewController {
    private let stack = UIStackView()
    private let status = UILabel()
    private let insert = UIButton(type: .system)
    private var generation = 0
    private var pending = false
    private var displayedLeaseID: String?
    override func viewDidLoad() {
        super.viewDidLoad(); overrideUserInterfaceStyle = .light
        view.backgroundColor = LensTheme.background
        stack.axis = .vertical; stack.spacing = 12; stack.translatesAutoresizingMaskIntoConstraints = false; view.addSubview(stack)
        NSLayoutConstraint.activate([stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 12),stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -12),stack.topAnchor.constraint(equalTo: view.topAnchor, constant: 8),stack.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -8)])
        let heading = UILabel(); heading.text = "观微 · 聊天建议"; heading.font = .preferredFont(forTextStyle: .headline); heading.adjustsFontForContentSizeCategory = true; heading.textColor = LensTheme.ink; stack.addArrangedSubview(heading)
        // Long drafts scroll inside the preview instead of pushing the switch key off screen.
        let preview = UIScrollView(); preview.backgroundColor = .white; preview.layer.cornerRadius = 12
        preview.alwaysBounceVertical = false; stack.addArrangedSubview(preview)
        status.numberOfLines = 0; status.font = .preferredFont(forTextStyle: .body); status.adjustsFontForContentSizeCategory = true; status.textColor = LensTheme.ink
        status.translatesAutoresizingMaskIntoConstraints = false; preview.addSubview(status)
        NSLayoutConstraint.activate([
            preview.heightAnchor.constraint(equalToConstant: 120),
            status.leadingAnchor.constraint(equalTo: preview.contentLayoutGuide.leadingAnchor, constant: 12),
            status.trailingAnchor.constraint(equalTo: preview.contentLayoutGuide.trailingAnchor, constant: -12),
            status.topAnchor.constraint(equalTo: preview.contentLayoutGuide.topAnchor, constant: 12),
            status.bottomAnchor.constraint(equalTo: preview.contentLayoutGuide.bottomAnchor, constant: -12),
            status.widthAnchor.constraint(equalTo: preview.frameLayoutGuide.widthAnchor, constant: -24)
        ])
        style(insert, primary: true); insert.setTitle("确认人物后插入", for: .normal)
        insert.addTarget(self, action: #selector(redeem), for: .touchUpInside); stack.addArrangedSubview(insert)
        let refresh = UIButton(type: .system); style(refresh, primary: false); refresh.setTitle("刷新批准草稿", for: .normal); refresh.addTarget(self, action: #selector(refreshDraft), for: .touchUpInside); stack.addArrangedSubview(refresh)
        let next = UIButton(type: .system); style(next, primary: false); next.setTitle("切回熟悉的输入法 🌐", for: .normal); next.addTarget(self, action: #selector(handleInputModeList(from:with:)), for: .allTouchEvents); stack.addArrangedSubview(next)
        refreshDraft()
    }
    private func style(_ button: UIButton, primary: Bool) {
        var configuration = primary ? UIButton.Configuration.filled() : UIButton.Configuration.tinted()
        configuration.baseBackgroundColor = primary ? LensTheme.green : LensTheme.tint
        configuration.baseForegroundColor = primary ? .white : LensTheme.green
        configuration.background.cornerRadius = 12
        configuration.contentInsets = NSDirectionalEdgeInsets(top: 12, leading: 16, bottom: 12, trailing: 16)
        button.configuration = configuration; button.titleLabel?.numberOfLines = 0
        button.titleLabel?.font = .preferredFont(forTextStyle: .body)
        button.titleLabel?.adjustsFontForContentSizeCategory = true
        button.heightAnchor.constraint(greaterThanOrEqualToConstant: 48).isActive = true
    }
    override func viewWillAppear(_ animated: Bool) { super.viewWillAppear(animated); generation += 1; refreshDraft() }
    override func viewWillDisappear(_ animated: Bool) { generation += 1; super.viewWillDisappear(animated) }
    override func textWillChange(_ textInput: UITextInput?) { generation += 1 }
    @objc private func refreshDraft() {
        guard !pending else { return }
        displayedLeaseID = nil
        guard hasFullAccess else { status.text = "未开启完全访问。建议仍可在主 App 查看；此键盘不会联网。"; insert.isEnabled = false; return }
        do { let lease = try LeaseStore.load(); displayedLeaseID = lease.lease_id; status.text = lease.draft; insert.setTitle("确认正在与「\(lease.person_name)」聊天并插入", for: .normal); insert.isEnabled = true }
        catch { status.text = "请先在主 App 批准草稿，30 秒内返回此处。"; insert.isEnabled = false }
    }
    @objc private func redeem() {
        guard hasFullAccess, !pending else { return }
        do {
            let lease = try LeaseStore.load()
            guard lease.lease_id == displayedLeaseID else { refreshDraft(); return }
            try LeaseStore.clear(); displayedLeaseID = nil
            guard let endpoint = lease.endpoint else { throw LensError.message("缺少服务地址") }
            let document = textDocumentProxy.documentIdentifier, revision = generation
            pending = true; insert.isEnabled = false
            Task { @MainActor in
                defer { pending = false }
                do {
                    let result = try await NativeHTTP.call(endpoint: endpoint, path: "redeem", body: ["lease_id": lease.lease_id, "secret": lease.secret, "confirmed": true])
                    guard hasFullAccess, revision == generation, document == textDocumentProxy.documentIdentifier, view.window != nil else { status.text = "输入框已变化，未插入，请重新准备草稿"; return }
                    guard let draft = result["draft"] as? String else { throw LensError.message("响应无效") }
                    textDocumentProxy.insertText(draft); status.text = "已插入，请检查并自行发送"
                } catch { status.text = error.localizedDescription }
            }
        } catch { status.text = error.localizedDescription }
    }
}
