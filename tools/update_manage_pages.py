import os

def create_manage_non_asn():
    src = r"c:\Users\ASUS\Web_Face_Recognation\src\pages\ManageASN.jsx"
    target = r"c:\Users\ASUS\Web_Face_Recognation\src\pages\ManageNonASN.jsx"
    
    with open(src, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Update for Non-ASN
    content = content.replace("const ManageASN = () => {", "const ManageNonASN = () => {")
    content = content.replace("export default ManageASN;", "export default ManageNonASN;")
    content = content.replace("Manajemen Data ASN", "Manajemen Data Non-ASN")
    content = content.replace("Kelola data biometrik dan profil pegawai ASN", "Kelola data biometrik dan profil pegawai Non-ASN")
    
    # Update fetch URL to include role=non_asn
    content = content.replace("axios.get('http://127.0.0.1:5000/api/manage-asn'", "axios.get('http://127.0.0.1:5000/api/manage-asn?role=non_asn'")
    
    with open(target, 'w', encoding='utf-8') as f:
        f.write(content)

def update_manage_asn():
    src = r"c:\Users\ASUS\Web_Face_Recognation\src\pages\ManageASN.jsx"
    
    with open(src, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Update fetch URL to include role=asn
    content = content.replace("axios.get('http://127.0.0.1:5000/api/manage-asn'", "axios.get('http://127.0.0.1:5000/api/manage-asn?role=asn'")
    
    with open(src, 'w', encoding='utf-8') as f:
        f.write(content)

if __name__ == "__main__":
    create_manage_non_asn()
    update_manage_asn()
    print("ManageASN updated and ManageNonASN created.")
